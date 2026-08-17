"""Transparent operational priority scoring.

The score answers one question: *where should limited management attention go
first?* It is a weighted, fully decomposable index - not a model. Every
component can be traced back to a published measure, and the contribution of
each component is stored alongside the total so the UI can always answer "why
this score?".

    Priority Score (0-100) =
        30%  Backlog growth pressure
      + 25%  Long-wait burden
      + 20%  18-week performance gap
      + 15%  Forecast deterioration risk
      + 10%  Trend persistence

Design decisions worth defending:

* Components are normalised **cross-sectionally within the latest reporting
  month**, so the score is a statement about relative position among peers in
  that month, not an absolute severity rating.
* Percentile ranking is used where only ordering is meaningful, and clipped
  robust scaling where magnitude carries information.
* Series below a configurable waiting-list floor are scored but excluded from
  headline rankings: a 40-pathway list can post a 50% growth rate from noise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.config import get_settings
from app.utils.logging import get_logger
from app.utils.mathx import clipped_robust_scale, percentile_rank

logger = get_logger(__name__)


@dataclass(frozen=True)
class Component:
    """One weighted component of the priority score."""

    key: str
    label: str
    weight: float
    description: str


COMPONENTS: tuple[Component, ...] = (
    Component(
        key="backlog_pressure",
        label="Backlog growth pressure",
        weight=30.0,
        description=(
            "Blends 3-month waiting-list growth with the 6-month trend slope "
            "expressed as a share of the current list."
        ),
    ),
    Component(
        key="long_wait_burden",
        label="Long-wait burden",
        weight=25.0,
        description=(
            "Share of the waiting list beyond the long-wait thresholds "
            "published for this period (52, 65 and 78 weeks where available)."
        ),
    ),
    Component(
        key="performance_gap",
        label="18-week performance gap",
        weight=20.0,
        description=(
            "Shortfall against the 92% within-18-weeks operational benchmark, "
            "combined with the recent direction of travel."
        ),
    ),
    Component(
        key="forecast_risk",
        label="Forecast deterioration risk",
        weight=15.0,
        description=(
            "Modelled percentage change in the waiting list over the next three "
            "months. Series without a forecast score neutrally."
        ),
    ),
    Component(
        key="persistence",
        label="Trend persistence",
        weight=10.0,
        description=(
            "How consistently the position has deteriorated across recent "
            "reporting months, rather than in a single month."
        ),
    ),
)

COMPONENT_WEIGHTS: dict[str, float] = {c.key: c.weight for c in COMPONENTS}

BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 25.0, "LOW"),
    (25.0, 50.0, "MODERATE"),
    (50.0, 75.0, "HIGH"),
    (75.0, 100.01, "CRITICAL"),
)

# Score assigned when a component cannot be computed for a series. Neutral by
# construction: a missing forecast should neither reward nor punish a service.
NEUTRAL_SCORE = 50.0


def band_for_score(score: float) -> str:
    """Map a 0-100 score onto its priority band."""
    if score is None or (isinstance(score, float) and np.isnan(score)):
        return "UNSCORED"
    for low, high, label in BANDS:
        if low <= score < high:
            return label
    return "CRITICAL"


def _backlog_pressure(snapshot: pd.DataFrame) -> pd.Series:
    """Growth over three months blended with the six-month trend."""
    growth = percentile_rank(snapshot["backlog_growth_3m_pct"])
    slope = percentile_rank(snapshot["trend_slope_6m_pct_of_list"])
    # Weighted towards the shorter window: operational teams act on what is
    # happening now, with the longer slope as corroboration.
    combined = growth.mul(0.65).add(slope.mul(0.35), fill_value=np.nan)
    combined = combined.where(growth.notna() & slope.notna(), growth.fillna(slope))
    return combined.fillna(NEUTRAL_SCORE)


def _long_wait_burden(snapshot: pd.DataFrame) -> pd.Series:
    """Percentile of long-wait share across whichever bands are populated."""
    available: list[pd.Series] = []
    weights: list[float] = []
    for column, weight in (
        ("pct_over_52_weeks", 0.5),
        ("pct_over_65_weeks", 0.3),
        ("pct_over_78_weeks", 0.2),
    ):
        if column not in snapshot.columns:
            continue
        values = pd.to_numeric(snapshot[column], errors="coerce")
        # A band that is zero nationwide (78+ weeks is largely eliminated)
        # carries no discriminating information; skip it rather than letting
        # percentile ranks of an all-zero column create phantom differences.
        if values.notna().sum() == 0 or float(values.fillna(0).max()) <= 0:
            continue
        available.append(percentile_rank(values))
        weights.append(weight)

    if not available:
        # Fall back to the share beyond 18 weeks, which is always published.
        return percentile_rank(
            pd.to_numeric(snapshot["pct_over_18_weeks"], errors="coerce")
        ).fillna(NEUTRAL_SCORE)

    total_weight = sum(weights)
    stacked = sum(s * (w / total_weight) for s, w in zip(available, weights, strict=False))
    return pd.Series(stacked, index=snapshot.index).fillna(NEUTRAL_SCORE)


def _performance_gap(snapshot: pd.DataFrame) -> pd.Series:
    """Shortfall against the 18-week benchmark plus direction of travel."""
    benchmark = get_settings().referral_to_treatment_benchmark
    within = pd.to_numeric(snapshot["pct_within_18_weeks"], errors="coerce")
    gap = (benchmark - within).clip(lower=0.0)
    # Magnitude matters here, so scale rather than rank.
    gap_score = clipped_robust_scale(gap)

    # Deterioration in the last three months adds to the gap signal.
    change = pd.to_numeric(
        snapshot.get("pct_within_18_weeks_change_3m"), errors="coerce"
    )
    deterioration = percentile_rank(-change) if change is not None else None

    if deterioration is None or deterioration.notna().sum() == 0:
        return gap_score.fillna(NEUTRAL_SCORE)
    blended = gap_score.mul(0.75).add(deterioration.mul(0.25), fill_value=np.nan)
    blended = blended.where(
        gap_score.notna() & deterioration.notna(), gap_score.fillna(deterioration)
    )
    return blended.fillna(NEUTRAL_SCORE)


def _forecast_risk(snapshot: pd.DataFrame) -> pd.Series:
    """Percentile of modelled 3-month growth; neutral where unavailable."""
    if "forecast_change_3m_pct" not in snapshot.columns:
        return pd.Series(NEUTRAL_SCORE, index=snapshot.index, dtype="float64")
    values = pd.to_numeric(snapshot["forecast_change_3m_pct"], errors="coerce")
    if "forecast_status" in snapshot.columns:
        values = values.where(snapshot["forecast_status"] == "ok")
    return percentile_rank(values).fillna(NEUTRAL_SCORE)


def _persistence(snapshot: pd.DataFrame) -> pd.Series:
    """Consistency of deterioration over recent months.

    Uses the share of the last six months in which the list grew, scaled
    directly to 0-100 (it is already a percentage), reinforced by the current
    consecutive run of rising months.
    """
    share = pd.to_numeric(snapshot.get("share_months_rising_6m"), errors="coerce")
    run = pd.to_numeric(snapshot.get("months_backlog_rising"), errors="coerce")
    # A run of 4+ consecutive rising months saturates the run component.
    run_score = (run.clip(lower=0, upper=4) / 4.0 * 100.0) if run is not None else None

    if share is None or share.notna().sum() == 0:
        return (
            run_score.fillna(NEUTRAL_SCORE)
            if run_score is not None
            else pd.Series(NEUTRAL_SCORE, index=snapshot.index, dtype="float64")
        )
    if run_score is None:
        return share.fillna(NEUTRAL_SCORE)
    blended = share.mul(0.6).add(run_score.mul(0.4), fill_value=np.nan)
    blended = blended.where(
        share.notna() & run_score.notna(), share.fillna(run_score)
    )
    return blended.fillna(NEUTRAL_SCORE)


_CALCULATORS = {
    "backlog_pressure": _backlog_pressure,
    "long_wait_burden": _long_wait_burden,
    "performance_gap": _performance_gap,
    "forecast_risk": _forecast_risk,
    "persistence": _persistence,
}


def score_snapshot(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Compute the priority score and its decomposition for one month.

    ``snapshot`` must be a single reporting month across all provider x
    specialty combinations, already joined to forecast columns.
    """
    if snapshot.empty:
        return snapshot.copy()

    settings = get_settings()
    result = snapshot.copy().reset_index(drop=True)

    # Scoring is relative, so the comparison set matters. Very small lists are
    # scored but marked non-rankable rather than dropped, so a user who filters
    # to a small service still sees a score with an explicit caveat.
    result["is_rankable"] = (
        pd.to_numeric(result["total_incomplete_pathways"], errors="coerce")
        >= settings.min_waiting_list_for_ranking
    )

    rankable = result[result["is_rankable"]]
    basis = rankable if len(rankable) >= 30 else result
    if len(rankable) < 30:
        logger.warning(
            "Only %d rankable series; scoring against the full population.",
            len(rankable),
        )

    total = pd.Series(0.0, index=result.index, dtype="float64")
    for component in COMPONENTS:
        raw = _CALCULATORS[component.key](basis)
        # Reindex the basis-derived scores back onto every row. Rows outside
        # the basis score neutrally on that component; they are then withheld
        # entirely below, because a score built purely from neutral defaults
        # carries no information.
        aligned = pd.Series(NEUTRAL_SCORE, index=result.index, dtype="float64")
        aligned.loc[raw.index] = raw.to_numpy()
        aligned = aligned.clip(lower=0.0, upper=100.0)

        result[f"score_{component.key}"] = aligned.round(1)
        contribution = aligned * (component.weight / 100.0)
        result[f"contribution_{component.key}"] = contribution.round(2)
        result[f"max_contribution_{component.key}"] = component.weight
        total = total + contribution

    scored = total.clip(lower=0.0, upper=100.0).round(1)

    # Services outside the scoring basis received NEUTRAL_SCORE on every
    # component, so their total is exactly 50 by construction - which would
    # otherwise present ~1,400 tiny services (including some with an empty
    # waiting list) as uniformly "HIGH" priority. That is an artefact, not a
    # finding, so they are reported as UNSCORED with their raw metrics intact.
    in_basis = result.index.isin(basis.index)
    result["priority_score"] = scored.where(in_basis)
    result["priority_band"] = [
        band_for_score(s) if ok else "UNSCORED"
        for s, ok in zip(result["priority_score"], in_basis, strict=True)
    ]
    result["priority_rank"] = (
        result["priority_score"]
        .where(result["is_rankable"])
        .rank(ascending=False, method="min")
    )

    withheld = int((~in_basis).sum())
    if withheld:
        logger.info(
            "%d services below the ranking threshold reported as UNSCORED",
            withheld,
        )
    return result


def component_metadata() -> list[dict]:
    """Component definitions, surfaced through the methodology endpoint."""
    return [
        {
            "key": c.key,
            "label": c.label,
            "weight": c.weight,
            "description": c.description,
        }
        for c in COMPONENTS
    ]


def band_metadata() -> list[dict]:
    """Band thresholds, surfaced through the methodology endpoint."""
    return [
        {"band": label, "min_score": low, "max_score": min(high, 100.0)}
        for low, high, label in BANDS
    ]
