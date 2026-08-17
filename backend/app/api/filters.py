"""Filter parsing and application.

Filters arrive as query parameters and are applied to in-memory frames. Values
are matched against the reference dimensions rather than interpolated into SQL,
so a filter value can never reach the query engine as text.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

VALID_BANDS = {"LOW", "MODERATE", "HIGH", "CRITICAL"}

SORTABLE_COLUMNS = {
    "priority_score",
    "total_incomplete_pathways",
    "backlog_growth_3m_pct",
    "backlog_growth_6m_pct",
    "pct_within_18_weeks",
    "pct_over_52_weeks",
    "over_52_weeks",
    "forecast_change_3m_pct",
    "forecast_3m",
    "provider_quality_score",
    "median_wait_weeks",
    "provider_name",
    "specialty_name",
}


def apply_filters(
    frame: pd.DataFrame,
    provider_code: str | None = None,
    specialty_code: str | None = None,
    region: str | None = None,
    priority_band: str | None = None,
    search: str | None = None,
    rankable_only: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Apply dashboard filters, returning the filtered frame and what was used."""
    result = frame
    applied: dict[str, Any] = {}

    if provider_code:
        result = result[result["provider_code"] == provider_code]
        applied["provider_code"] = provider_code
    if specialty_code:
        result = result[result["specialty_code"] == specialty_code]
        applied["specialty_code"] = specialty_code
    if region:
        # Accept either the region code or its display name.
        mask = pd.Series(False, index=result.index)
        if "region_code" in result.columns:
            mask = mask | (result["region_code"] == region)
        if "region_name" in result.columns:
            mask = mask | (result["region_name"] == region)
        result = result[mask]
        applied["region"] = region
    if priority_band:
        band = priority_band.upper()
        if band in VALID_BANDS:
            result = result[result["priority_band"] == band]
            applied["priority_band"] = band
    if search:
        term = search.strip().lower()
        if term:
            haystack = (
                result["provider_name"].fillna("").str.lower()
                + " "
                + result["specialty_name"].fillna("").str.lower()
            )
            result = result[haystack.str.contains(term, regex=False)]
            applied["search"] = search.strip()
    if rankable_only and "is_rankable" in result.columns:
        result = result[result["is_rankable"]]
        applied["rankable_only"] = True

    return result, applied


def apply_sort(
    frame: pd.DataFrame, sort_by: str | None, descending: bool = True
) -> pd.DataFrame:
    """Sort by an allow-listed column, defaulting to priority score."""
    column = sort_by if sort_by in SORTABLE_COLUMNS else "priority_score"
    if column not in frame.columns:
        return frame
    return frame.sort_values(
        column, ascending=not descending, na_position="last", kind="mergesort"
    )
