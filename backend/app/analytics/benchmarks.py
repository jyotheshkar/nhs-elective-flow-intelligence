"""Peer benchmarking.

Medians rather than means throughout: waiting-list distributions across 150
providers are strongly right-skewed, and a mean would be dragged by a handful
of very large organisations.

These are *peer benchmarks* computed from the loaded data. They are not
official NHS England benchmarks and are labelled as such wherever they surface.
"""

from __future__ import annotations

import pandas as pd

BENCHMARK_MEASURES = (
    "total_incomplete_pathways",
    "pct_within_18_weeks",
    "pct_over_52_weeks",
    "backlog_growth_3m_pct",
    "priority_score",
)


def build_benchmarks(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Specialty-level peer medians across all providers in the latest month."""
    if snapshot.empty:
        return pd.DataFrame()

    rankable = snapshot[snapshot.get("is_rankable", True)]
    basis = rankable if not rankable.empty else snapshot

    measures = [m for m in BENCHMARK_MEASURES if m in basis.columns]
    specialty = (
        basis.groupby("specialty_code")[measures]
        .median()
        .add_prefix("peer_median_")
        .reset_index()
    )
    national = basis[measures].median().to_dict()
    for measure in measures:
        specialty[f"national_median_{measure}"] = national[measure]
    return specialty


def attach_benchmarks(
    snapshot: pd.DataFrame, benchmarks: pd.DataFrame
) -> pd.DataFrame:
    """Left-join peer and national medians onto a snapshot."""
    if benchmarks.empty or snapshot.empty:
        return snapshot
    return snapshot.merge(benchmarks, on="specialty_code", how="left")


def comparison_frame(
    snapshot: pd.DataFrame, provider_codes: list[str], specialty_code: str
) -> pd.DataFrame:
    """Side-by-side rows for the provider comparison page."""
    mask = snapshot["provider_code"].isin(provider_codes) & (
        snapshot["specialty_code"] == specialty_code
    )
    return snapshot[mask].sort_values("priority_score", ascending=False)
