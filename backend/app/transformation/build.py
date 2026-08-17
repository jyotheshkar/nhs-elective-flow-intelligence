"""Construction of the canonical star schema.

Produces four tables from the cleaned workbook frames:

    dim_provider    one row per provider organisation
    dim_specialty   one row per treatment function
    dim_date        one row per reporting month
    fact_rtt        one row per provider x specialty x reporting month

The waiting-list (incomplete) dataset defines the fact grain. Activity datasets
are left-joined onto it, so a month with no published activity file yields null
activity rather than dropping waiting-list rows.
"""

from __future__ import annotations

import pandas as pd

from app.config import get_region_lookup
from app.transformation.cleaning import (
    short_provider_name,
    short_specialty_name,
    title_case_provider,
)
from app.transformation.schema import DATA_SOURCE_OFFICIAL
from app.utils.logging import get_logger
from app.utils.mathx import safe_divide

logger = get_logger(__name__)

# Specialty codes beginning with 'X' are the "Other - ..." groupings; the C_
# codes are individual treatment functions.
_SURGICAL_CODES = {
    "C_100", "C_101", "C_110", "C_120", "C_130",
    "C_140", "C_150", "C_160", "C_170", "C_502",
}
_MEDICAL_CODES = {
    "C_300", "C_301", "C_320", "C_330", "C_340",
    "C_400", "C_410", "C_430",
}


def _specialty_group(code: str, name: str | None) -> str:
    """Assign a coarse grouping used for peer benchmarking."""
    code = (code or "").upper()
    if code in _SURGICAL_CODES:
        return "Surgical"
    if code in _MEDICAL_CODES:
        return "Medical"
    if code.startswith("X"):
        lowered = (name or "").lower()
        if "surgical" in lowered:
            return "Surgical"
        if "medical" in lowered:
            return "Medical"
        if "mental" in lowered:
            return "Mental Health"
        if "paediatric" in lowered:
            return "Paediatrics"
        return "Other"
    return "Other"


def build_dim_provider(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per provider, using the most recent published name."""
    columns = ["provider_code", "provider_name", "region_code", "reporting_month"]
    stacked = pd.concat(
        [f[[c for c in columns if c in f.columns]] for f in frames if not f.empty],
        ignore_index=True,
    )
    stacked = stacked.dropna(subset=["provider_code"])
    stacked = stacked.sort_values("reporting_month")
    latest = stacked.groupby("provider_code", as_index=False).last()

    regions = get_region_lookup()
    latest["region_name"] = (
        latest["region_code"].map(regions).fillna(latest["region_code"])
    )
    latest["provider_name"] = latest["provider_name"].map(title_case_provider)
    latest["provider_short_name"] = latest["provider_name"].map(short_provider_name)
    latest["provider_type"] = latest["provider_name"].map(_provider_type)
    return latest[
        [
            "provider_code", "provider_name", "provider_short_name",
            "region_code", "region_name", "provider_type",
        ]
    ].sort_values("provider_name").reset_index(drop=True)


def _provider_type(name: str | None) -> str:
    """Classify from the published name; NHS England does not publish a type
    column in the RTT provider files."""
    if not name:
        return "Unknown"
    lowered = str(name).lower()
    if "foundation trust" in lowered:
        return "NHS Foundation Trust"
    if "nhs trust" in lowered:
        return "NHS Trust"
    return "Other provider"


def build_dim_specialty(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per treatment function."""
    columns = ["specialty_code", "specialty_name", "reporting_month"]
    stacked = pd.concat(
        [f[[c for c in columns if c in f.columns]] for f in frames if not f.empty],
        ignore_index=True,
    )
    stacked = stacked.dropna(subset=["specialty_code"]).sort_values("reporting_month")
    latest = stacked.groupby("specialty_code", as_index=False).last()
    latest["specialty_name"] = latest["specialty_name"].astype("string")
    latest["specialty_short_name"] = latest["specialty_name"].map(
        short_specialty_name
    )
    latest["specialty_group"] = [
        _specialty_group(c, n)
        for c, n in zip(latest["specialty_code"], latest["specialty_name"], strict=False)
    ]
    return latest[
        ["specialty_code", "specialty_name", "specialty_short_name", "specialty_group"]
    ].sort_values("specialty_name").reset_index(drop=True)


def build_dim_date(months: list[pd.Timestamp]) -> pd.DataFrame:
    """Calendar dimension including the NHS financial year (April-March)."""
    unique = sorted({pd.Timestamp(m).normalize().replace(day=1) for m in months})
    rows = []
    for index, month in enumerate(unique):
        fy_start = month.year if month.month >= 4 else month.year - 1
        rows.append(
            {
                "reporting_month": month,
                "month_label": month.strftime("%b %Y"),
                "month_key": month.strftime("%Y-%m"),
                "year": int(month.year),
                "month_number": int(month.month),
                "quarter": f"Q{((month.month - 1) // 3) + 1}",
                "financial_year": f"{fy_start}/{str(fy_start + 1)[-2:]}",
                "financial_quarter": f"Q{(((month.month - 4) % 12) // 3) + 1}",
                "month_index": index,
                "is_latest": index == len(unique) - 1,
            }
        )
    return pd.DataFrame(rows)


def build_fact_rtt(
    incomplete: pd.DataFrame,
    admitted: pd.DataFrame | None,
    non_admitted: pd.DataFrame | None,
    data_source_type: str = DATA_SOURCE_OFFICIAL,
) -> pd.DataFrame:
    """Assemble the canonical fact table at provider x specialty x month."""
    if incomplete.empty:
        raise ValueError("Cannot build fact_rtt: the waiting-list frame is empty.")

    keys = ["provider_code", "specialty_code", "reporting_month"]
    fact = incomplete.copy()

    for activity, measure in (
        (admitted, "admitted_activity"),
        (non_admitted, "non_admitted_activity"),
    ):
        if activity is None or activity.empty or measure not in activity.columns:
            fact[measure] = pd.NA
            logger.warning("No %s data available; column left null.", measure)
            continue
        subset = activity[[*keys, measure]].drop_duplicates(subset=keys, keep="last")
        fact = fact.merge(subset, on=keys, how="left")

    fact["admitted_activity"] = pd.to_numeric(fact["admitted_activity"], errors="coerce")
    fact["non_admitted_activity"] = pd.to_numeric(
        fact["non_admitted_activity"], errors="coerce"
    )
    # Total completed activity. Summed with min_count=1 so a row where both
    # components are missing stays null rather than collapsing to zero.
    fact["completed_pathways"] = fact[
        ["admitted_activity", "non_admitted_activity"]
    ].sum(axis=1, min_count=1)

    total = pd.to_numeric(fact["total_incomplete_pathways"], errors="coerce")
    within = pd.to_numeric(fact["within_18_weeks"], errors="coerce")
    fact["total_incomplete_pathways"] = total
    fact["within_18_weeks"] = within
    fact["over_18_weeks"] = (total - within).clip(lower=0)

    for column in ("over_52_weeks", "over_65_weeks", "over_78_weeks",
                   "over_104_weeks", "median_wait_weeks",
                   "percentile_92_wait_weeks"):
        if column in fact.columns:
            fact[column] = pd.to_numeric(fact[column], errors="coerce")
        else:
            fact[column] = pd.NA

    # Percentages recomputed from counts so the definition is ours and testable,
    # rather than inheriting whatever rounding the publication applied.
    fact["pct_within_18_weeks"] = safe_divide(within, total) * 100.0
    fact["pct_over_18_weeks"] = safe_divide(fact["over_18_weeks"], total) * 100.0
    for band in ("52", "65", "78", "104"):
        fact[f"pct_over_{band}_weeks"] = (
            safe_divide(fact[f"over_{band}_weeks"], total) * 100.0
        )

    fact["data_source_type"] = data_source_type
    fact["reporting_month"] = pd.to_datetime(fact["reporting_month"])
    fact["month_key"] = fact["reporting_month"].dt.strftime("%Y-%m")

    ordered = [
        "provider_code", "specialty_code", "reporting_month", "month_key",
        "total_incomplete_pathways", "within_18_weeks", "over_18_weeks",
        "over_52_weeks", "over_65_weeks", "over_78_weeks", "over_104_weeks",
        "pct_within_18_weeks", "pct_over_18_weeks", "pct_over_52_weeks",
        "pct_over_65_weeks", "pct_over_78_weeks", "pct_over_104_weeks",
        "median_wait_weeks", "percentile_92_wait_weeks",
        "admitted_activity", "non_admitted_activity", "completed_pathways",
        "data_source_type",
    ]
    # Carry the source-published percentages through for reconciliation checks.
    for extra in ("pct_within_18_weeks_source", "pct_over_52_weeks_source"):
        if extra in fact.columns:
            ordered.append(extra)

    fact = fact[[c for c in ordered if c in fact.columns]]
    return fact.sort_values(
        ["provider_code", "specialty_code", "reporting_month"]
    ).reset_index(drop=True)
