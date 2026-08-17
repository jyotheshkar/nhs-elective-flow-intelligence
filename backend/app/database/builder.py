"""Warehouse assembly: metrics, forecasts, scores and quality in one pass.

Called by ``scripts/build_warehouse.py``. Kept out of the API process so the
expensive work (forecasting ~3,000 series) happens once at build time and the
API only ever reads precomputed tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.analytics.benchmarks import attach_benchmarks, build_benchmarks
from app.analytics.metrics import add_trend_metrics, latest_snapshot
from app.analytics.priority import score_snapshot
from app.config import get_settings
from app.database.warehouse import build_warehouse
from app.forecasting.engine import forecast_all
from app.forecasting.validation import summarise_backtests
from app.quality.score import build_quality_report, provider_quality_scores
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BuildResult:
    """Summary of a warehouse build, printed by the build script."""

    warehouse_path: Path
    row_counts: dict[str, int]
    latest_month: str
    reporting_months: int
    data_source_type: str
    quality_score: float
    forecast_summary: dict
    messages: list[str]


def build_all(
    fact: pd.DataFrame,
    dim_provider: pd.DataFrame,
    dim_specialty: pd.DataFrame,
    dim_date: pd.DataFrame,
    audit: pd.DataFrame,
    messages: list[str] | None = None,
) -> BuildResult:
    """Run the analytical build and materialise the warehouse."""
    settings = get_settings()
    messages = list(messages or [])

    logger.info("Deriving longitudinal metrics")
    metrics = add_trend_metrics(fact)

    logger.info("Generating forecasts")
    forecasts = forecast_all(
        metrics, min_latest_waiting_list=settings.min_waiting_list_for_ranking
    )
    forecast_summary = summarise_backtests(forecasts)

    logger.info("Scoring operational priority")
    snapshot = latest_snapshot(metrics)
    if not forecasts.empty:
        snapshot = snapshot.merge(
            forecasts, on=["provider_code", "specialty_code"], how="left"
        )
    priority = score_snapshot(snapshot)

    benchmarks = build_benchmarks(priority)
    priority = attach_benchmarks(priority, benchmarks)

    logger.info("Running data quality checks")
    quality = build_quality_report(fact, dim_provider, dim_specialty)
    quality_issues = quality.issue_frame()
    provider_quality = provider_quality_scores(quality_issues, fact)

    latest_month = (
        pd.Timestamp(fact["reporting_month"].max()).strftime("%Y-%m")
        if not fact.empty
        else ""
    )
    data_source_type = (
        str(fact["data_source_type"].iloc[0]) if not fact.empty else "UNKNOWN"
    )

    metadata = pd.DataFrame(
        [
            {
                "app_version": settings.app_version,
                "built_at": datetime.now(UTC).isoformat(),
                "data_source_type": data_source_type,
                "data_mode": settings.app_data_mode,
                "latest_reporting_month": latest_month,
                "reporting_months": int(len(dim_date)),
                "provider_count": int(len(dim_provider)),
                "specialty_count": int(len(dim_specialty)),
                "fact_rows": int(len(fact)),
                "quality_score": float(quality.overall_score),
                "forecast_series_ok": int(forecast_summary["series_forecast"]),
                "forecast_series_insufficient": int(
                    forecast_summary["series_insufficient_history"]
                ),
                "forecast_median_mape": forecast_summary["median_mape"],
                "forecast_share_beating_naive": forecast_summary[
                    "share_beating_naive"
                ],
                "referral_to_treatment_benchmark": (
                    settings.referral_to_treatment_benchmark
                ),
                "min_waiting_list_for_ranking": (
                    settings.min_waiting_list_for_ranking
                ),
                "build_messages": " | ".join(messages),
            }
        ]
    )

    frames = {
        "dim_provider": dim_provider,
        "dim_specialty": dim_specialty,
        "dim_date": dim_date,
        "fact_rtt": fact,
        "fact_rtt_metrics": metrics,
        "fact_forecast": forecasts,
        "fact_priority": priority,
        "fact_quality_issues": quality_issues,
        "dim_provider_quality": provider_quality,
        "ingestion_audit": audit if audit is not None else pd.DataFrame(),
        "warehouse_metadata": metadata,
    }

    path = build_warehouse(frames)
    return BuildResult(
        warehouse_path=path,
        row_counts={name: len(frame) for name, frame in frames.items()},
        latest_month=latest_month,
        reporting_months=len(dim_date),
        data_source_type=data_source_type,
        quality_score=quality.overall_score,
        forecast_summary=forecast_summary,
        messages=messages,
    )
