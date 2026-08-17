"""Illustrative capacity/activity scenario modelling.

WHAT THIS IS
    A transparent accounting projection. It asks: *if this service completed
    x% more pathways per month than it recently has, and everything else
    behaved as the baseline forecast assumes, how would the modelled waiting
    list differ?*

WHAT THIS IS NOT
    Causal inference. It cannot tell you that adding capacity *will* reduce the
    list by this amount. Additional activity changes referral behaviour,
    validation practice and case mix in ways this model does not represent, and
    no counterfactual is identified anywhere in the published data.

THE MODEL
    baseline_backlog(h)  = forecast model output at horizon h
    additional_activity  = uplift_pct/100 * recent_monthly_activity
    scenario_backlog(h)  = max(0, baseline_backlog(h) - h * additional_activity)

Cumulative because each additional month of higher activity removes further
pathways from the list. Floored at zero because a waiting list cannot be
negative. Every output is labelled as a modelled estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_UPLIFTS = (0.0, 5.0, 10.0, 15.0, 20.0)
MAX_UPLIFT_PCT = 100.0


@dataclass
class ScenarioPoint:
    """Modelled backlog at one horizon under one uplift assumption."""

    horizon_months: int
    month: str | None
    baseline_backlog: float
    scenario_backlog: float
    difference_from_baseline: float
    additional_activity_cumulative: float


@dataclass
class ScenarioResult:
    """A complete scenario run for one provider x specialty."""

    provider_code: str
    specialty_code: str
    status: str
    uplift_pct: float
    baseline_monthly_activity: float | None
    additional_monthly_activity: float | None
    points: list[ScenarioPoint] = field(default_factory=list)
    uplift_required_to_stabilise_pct: float | None = None
    stabilisation_feasible: bool = False
    assumptions: list[str] = field(default_factory=list)
    message: str = ""


UNAVAILABLE_NO_FORECAST = "no_forecast"
UNAVAILABLE_NO_ACTIVITY = "no_activity_data"
STATUS_OK = "ok"

_ASSUMPTIONS = [
    "Baseline is the selected forecast model's projection of the waiting list, "
    "extrapolating recent behaviour.",
    "The activity uplift is applied to the average monthly completed pathways "
    "over the most recent three reporting months.",
    "Additional completed activity is assumed to remove pathways from the "
    "waiting list one-for-one, and to accumulate month on month.",
    "Referral behaviour, case mix, validation activity and clinical urgency are "
    "assumed unchanged. In practice additional capacity can change all of them.",
    "Workforce, estate, theatre and diagnostic constraints are not represented; "
    "the model does not assess whether an uplift is achievable.",
    "Results are modelled estimates for discussion, not predicted outcomes.",
]


def _recent_activity(history: pd.DataFrame, months: int = 3) -> float:
    """Mean monthly completed pathways over the most recent months."""
    ordered = history.sort_values("reporting_month")
    activity = pd.to_numeric(ordered["completed_pathways"], errors="coerce").dropna()
    if activity.empty:
        return float("nan")
    return float(activity.tail(months).mean())


def run_scenario(
    history: pd.DataFrame,
    forecast_row: pd.Series | dict,
    uplift_pct: float,
    horizons: tuple[int, ...] = (1, 3, 6),
) -> ScenarioResult:
    """Run one uplift scenario against a baseline forecast."""
    provider = str(
        history["provider_code"].iloc[0] if not history.empty else "")
    specialty = str(
        history["specialty_code"].iloc[0] if not history.empty else "")

    uplift_pct = float(np.clip(uplift_pct, 0.0, MAX_UPLIFT_PCT))
    row = dict(forecast_row) if forecast_row is not None else {}

    if row.get("forecast_status") != "ok":
        return ScenarioResult(
            provider_code=provider,
            specialty_code=specialty,
            status=UNAVAILABLE_NO_FORECAST,
            uplift_pct=uplift_pct,
            baseline_monthly_activity=None,
            additional_monthly_activity=None,
            assumptions=_ASSUMPTIONS,
            message=(
                "No baseline forecast is available for this service, so a "
                "scenario cannot be projected. "
                + str(row.get("forecast_message") or "")
            ).strip(),
        )

    baseline_activity = _recent_activity(history)
    if not np.isfinite(baseline_activity) or baseline_activity <= 0:
        return ScenarioResult(
            provider_code=provider,
            specialty_code=specialty,
            status=UNAVAILABLE_NO_ACTIVITY,
            uplift_pct=uplift_pct,
            baseline_monthly_activity=None,
            additional_monthly_activity=None,
            assumptions=_ASSUMPTIONS,
            message=(
                "No completed-activity data is published for this service in "
                "the loaded period, so an activity uplift cannot be modelled."
            ),
        )

    additional_monthly = baseline_activity * (uplift_pct / 100.0)

    points: list[ScenarioPoint] = []
    for horizon in horizons:
        baseline = row.get(f"forecast_{horizon}m")
        if baseline is None or not np.isfinite(float(baseline)):
            continue
        baseline = float(baseline)
        cumulative_extra = additional_monthly * horizon
        scenario = max(0.0, baseline - cumulative_extra)
        points.append(
            ScenarioPoint(
                horizon_months=horizon,
                month=row.get(f"forecast_{horizon}m_month"),
                baseline_backlog=round(baseline, 1),
                scenario_backlog=round(scenario, 1),
                difference_from_baseline=round(scenario - baseline, 1),
                additional_activity_cumulative=round(cumulative_extra, 1),
            )
        )

    required, feasible = _uplift_to_stabilise(row, baseline_activity)

    return ScenarioResult(
        provider_code=provider,
        specialty_code=specialty,
        status=STATUS_OK,
        uplift_pct=uplift_pct,
        baseline_monthly_activity=round(baseline_activity, 1),
        additional_monthly_activity=round(additional_monthly, 1),
        points=points,
        uplift_required_to_stabilise_pct=required,
        stabilisation_feasible=feasible,
        assumptions=_ASSUMPTIONS,
    )


def _uplift_to_stabilise(
    row: dict, baseline_activity: float, horizon: int = 3
) -> tuple[float | None, bool]:
    """Uplift that would hold the list at its current level over ``horizon``.

    Solving ``baseline_forecast - horizon * activity * u/100 = current_list``
    for u. Returns ``(None, False)`` when the list is already forecast to fall,
    since no uplift is needed to stabilise it.
    """
    current = row.get("forecast_last_actual")
    projected = row.get(f"forecast_{horizon}m")
    if current is None or projected is None:
        return None, False
    current = float(current)
    projected = float(projected)
    if not np.isfinite(current) or not np.isfinite(projected):
        return None, False

    growth = projected - current
    if growth <= 0:
        # Already stable or improving on the baseline projection.
        return 0.0, True
    if baseline_activity <= 0:
        return None, False

    required = growth / (horizon * baseline_activity) * 100.0
    # Beyond a doubling of activity the arithmetic is still valid but the
    # answer stops being operationally meaningful, so it is flagged.
    return round(float(required), 1), bool(required <= MAX_UPLIFT_PCT)


def run_scenario_set(
    history: pd.DataFrame,
    forecast_row: pd.Series | dict,
    uplifts: tuple[float, ...] = DEFAULT_UPLIFTS,
    horizons: tuple[int, ...] = (1, 3, 6),
) -> list[ScenarioResult]:
    """Run the standard uplift ladder for one service."""
    return [
        run_scenario(history, forecast_row, uplift, horizons) for uplift in uplifts
    ]


def scenario_assumptions() -> list[str]:
    """The assumption list, surfaced in the UI alongside every scenario."""
    return list(_ASSUMPTIONS)
