"""Read-side data access.

All warehouse reads funnel through here so query text, caching and the
"warehouse missing" failure mode live in one place. The API layer never touches
DuckDB directly.

Caching strategy: the warehouse is immutable between builds, so the reference
tables and the latest-month snapshot are loaded once and held in memory.
Time-series queries are cached per key. This keeps the dashboard fast without
introducing a cache-invalidation problem - a rebuild restarts the process.
"""

from __future__ import annotations

import functools
import threading
from typing import Any

import numpy as np
import pandas as pd

from app.config import get_settings, get_source_config
from app.database import warehouse
from app.utils.logging import get_logger

logger = get_logger(__name__)

_LOCK = threading.Lock()


class WarehouseUnavailable(RuntimeError):
    """Raised when the warehouse has not been built."""


def warehouse_available() -> bool:
    return warehouse.warehouse_exists()


def require_warehouse() -> None:
    if not warehouse_available():
        raise WarehouseUnavailable(
            "Official data is currently unavailable. Run 'make data' to build "
            "the warehouse, or switch to demo mode with 'make demo'."
        )


def clear_caches() -> None:
    """Drop every cached frame. Used by tests and after a rebuild."""
    for func in (
        load_metadata, load_providers, load_specialties, load_periods,
        load_snapshot, load_quality_issues, load_audit_table,
        load_national_trend, load_regions, load_fact_table, load_quality_report,
    ):
        func.cache_clear()
    _history_cache.clear()


@functools.lru_cache(maxsize=1)
def load_metadata() -> dict[str, Any]:
    """Single-row warehouse metadata as a plain dict."""
    require_warehouse()
    frame = warehouse.query("SELECT * FROM warehouse_metadata LIMIT 1")
    if frame.empty:
        return {}
    return _clean_record(frame.iloc[0].to_dict())


@functools.lru_cache(maxsize=1)
def load_providers() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query(
        "SELECT * FROM dim_provider ORDER BY provider_name"
    )


@functools.lru_cache(maxsize=1)
def load_specialties() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query(
        "SELECT * FROM dim_specialty ORDER BY specialty_name"
    )


@functools.lru_cache(maxsize=1)
def load_regions() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query(
        """
        SELECT DISTINCT region_code, region_name
        FROM dim_provider
        WHERE region_code IS NOT NULL
        ORDER BY region_name
        """
    )


@functools.lru_cache(maxsize=1)
def load_periods() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query(
        "SELECT * FROM dim_date ORDER BY reporting_month DESC"
    )


@functools.lru_cache(maxsize=1)
def load_snapshot() -> pd.DataFrame:
    """Latest reporting month with scores, forecasts and benchmarks attached."""
    require_warehouse()
    frame = warehouse.query("SELECT * FROM vw_latest_performance")
    if "is_rankable" in frame.columns:
        frame["is_rankable"] = frame["is_rankable"].astype(bool)
    return frame


@functools.lru_cache(maxsize=1)
def load_quality_issues() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query("SELECT * FROM vw_data_quality")


@functools.lru_cache(maxsize=1)
def load_audit_table() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query(
        "SELECT * FROM ingestion_audit ORDER BY reporting_period DESC"
    )


@functools.lru_cache(maxsize=1)
def load_national_trend() -> pd.DataFrame:
    require_warehouse()
    return warehouse.query("SELECT * FROM vw_national_trend ORDER BY reporting_month")


@functools.lru_cache(maxsize=1)
def load_fact_table() -> pd.DataFrame:
    """The full fact table. Held once: it is ~60k rows and immutable."""
    require_warehouse()
    return warehouse.query("SELECT * FROM fact_rtt")


@functools.lru_cache(maxsize=1)
def load_quality_report():
    """Recomputed quality report, cached for the life of the process.

    The dimension scores must agree with what the build produced, so they are
    recomputed from the same fact table rather than stored as loose numbers.
    Running the anomaly and completeness checks over 60k rows takes ~4 seconds,
    which is fine once at first request but not on every page view.
    """
    from app.quality.score import build_quality_report

    return build_quality_report(
        load_fact_table(), load_providers(), load_specialties()
    )


_history_cache: dict[tuple, pd.DataFrame] = {}

_HISTORY_COLUMNS = """
    month_key, reporting_month, total_incomplete_pathways, within_18_weeks,
    pct_within_18_weeks, over_52_weeks, pct_over_52_weeks, over_18_weeks,
    pct_over_18_weeks, median_wait_weeks, completed_pathways,
    admitted_activity, non_admitted_activity, backlog_change_1m,
    backlog_growth_1m_pct, backlog_growth_3m_pct, rolling_activity_3m,
    activity_change_3m_pct, months_backlog_rising, implied_additions
"""


def load_service_history(provider_code: str, specialty_code: str) -> pd.DataFrame:
    """Monthly history for one provider x specialty."""
    require_warehouse()
    key = ("service", provider_code, specialty_code)
    with _LOCK:
        cached = _history_cache.get(key)
    if cached is not None:
        return cached

    frame = warehouse.query(
        f"""
        SELECT {_HISTORY_COLUMNS}
        FROM vw_provider_specialty_trends
        WHERE provider_code = ? AND specialty_code = ?
        ORDER BY reporting_month
        """,
        [provider_code, specialty_code],
    )
    with _LOCK:
        # Bounded so a crawler hitting every service cannot grow this without
        # limit; the working set for a browsing session is far smaller.
        if len(_history_cache) > 800:
            _history_cache.clear()
        _history_cache[key] = frame
    return frame


def load_provider_history(provider_code: str) -> pd.DataFrame:
    """Monthly totals for one provider across all specialties."""
    require_warehouse()
    key = ("provider", provider_code)
    with _LOCK:
        cached = _history_cache.get(key)
    if cached is not None:
        return cached

    frame = warehouse.query(
        """
        SELECT
            month_key,
            reporting_month,
            SUM(total_incomplete_pathways) AS total_incomplete_pathways,
            SUM(within_18_weeks)           AS within_18_weeks,
            SUM(over_52_weeks)             AS over_52_weeks,
            SUM(completed_pathways)        AS completed_pathways,
            CASE WHEN SUM(total_incomplete_pathways) > 0
                 THEN SUM(within_18_weeks) * 100.0
                      / SUM(total_incomplete_pathways) END
                AS pct_within_18_weeks,
            CASE WHEN SUM(total_incomplete_pathways) > 0
                 THEN SUM(over_52_weeks) * 100.0
                      / SUM(total_incomplete_pathways) END
                AS pct_over_52_weeks
        FROM vw_provider_specialty_trends
        WHERE provider_code = ?
        GROUP BY month_key, reporting_month
        ORDER BY reporting_month
        """,
        [provider_code],
    )
    with _LOCK:
        _history_cache[key] = frame
    return frame


def load_forecast_row(provider_code: str, specialty_code: str) -> dict[str, Any]:
    """Forecast record for one service."""
    require_warehouse()
    frame = warehouse.query(
        """
        SELECT * FROM fact_forecast
        WHERE provider_code = ? AND specialty_code = ?
        LIMIT 1
        """,
        [provider_code, specialty_code],
    )
    if frame.empty:
        return {}
    return _clean_record(frame.iloc[0].to_dict())


def service_row(provider_code: str, specialty_code: str) -> dict[str, Any] | None:
    """One row from the latest-month snapshot."""
    snapshot = load_snapshot()
    mask = (snapshot["provider_code"] == provider_code) & (
        snapshot["specialty_code"] == specialty_code
    )
    matched = snapshot[mask]
    if matched.empty:
        return None
    return _clean_record(matched.iloc[0].to_dict())


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    """Convert NaN/NaT/numpy scalars into JSON-safe Python values."""
    cleaned: dict[str, Any] = {}
    for key, value in record.items():
        cleaned[key] = _clean_value(value)
    return cleaned


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, np.bool_ | bool):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating | float):
        return None if not np.isfinite(float(value)) else float(value)
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if value is pd.NaT:
        return None
    if isinstance(value, np.ndarray):
        return [_clean_value(v) for v in value.tolist()]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame -> list of JSON-safe dicts."""
    if frame is None or frame.empty:
        return []
    return [_clean_record(r) for r in frame.to_dict(orient="records")]


def source_metadata() -> dict[str, Any]:
    """Source descriptors from config/sources.yaml."""
    try:
        rtt = get_source_config()["sources"]["rtt"]
    except (FileNotFoundError, KeyError):
        return {}
    return {
        "source_name": rtt.get("name"),
        "source_landing_page": rtt.get("landing_page"),
        "licence": rtt.get("licence"),
        "attribution": rtt.get("attribution"),
    }


def build_provenance() -> dict[str, Any]:
    """Assemble the provenance block shown across the UI."""
    settings = get_settings()
    source = source_metadata()

    if not warehouse_available():
        return {
            "data_source_type": "UNAVAILABLE",
            "data_mode": settings.app_data_mode,
            "is_demo": settings.app_data_mode == "demo",
            "reporting_months": 0,
            **source,
        }

    metadata = load_metadata()
    periods = load_periods()
    audit = load_audit_table()

    latest = metadata.get("latest_reporting_month")
    latest_label = None
    earliest = None
    if not periods.empty:
        latest_row = periods.iloc[0]
        latest_label = latest_row.get("month_label")
        earliest = periods.iloc[-1].get("month_key")

    retrieved_at = None
    published = None
    if not audit.empty:
        processed = audit[audit["processing_status"] == "processed"]
        if not processed.empty:
            retrieved_at = str(processed["downloaded_at"].max() or "") or None
            published_values = processed["published_date"].dropna()
            if not published_values.empty:
                published = str(published_values.iloc[0])

    data_source_type = str(metadata.get("data_source_type") or "UNKNOWN")
    is_demo = data_source_type == "DEMO_SYNTHETIC"

    return {
        "data_source_type": data_source_type,
        "data_mode": "demo" if is_demo else "official",
        "is_demo": is_demo,
        "source_name": (
            "Synthetic demonstration dataset (not NHS England data)"
            if is_demo
            else source.get("source_name")
            or "NHS England Consultant-led RTT Waiting Times"
        ),
        "source_landing_page": None if is_demo else source.get("source_landing_page"),
        "licence": None if is_demo else source.get("licence"),
        "attribution": (
            "Generated synthetic data - illustrative only."
            if is_demo
            else source.get("attribution")
        ),
        "latest_reporting_month": latest,
        "latest_reporting_month_label": latest_label,
        "reporting_months": int(metadata.get("reporting_months") or len(periods)),
        "earliest_reporting_month": earliest,
        "retrieved_at": retrieved_at,
        "published_date": published,
        "built_at": metadata.get("built_at"),
        "source_files": int(len(audit)) if not audit.empty else 0,
    }
