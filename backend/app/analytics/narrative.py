"""Deterministic management briefing generation.

Every sentence is assembled from computed values. There is no language model in
this path and no template that can assert something the data does not support:
if a metric is missing, the corresponding sentence is omitted rather than
filled with a plausible-sounding default.

This is the "AI/automation" surface of the product in the honest sense -
automated generation of evidence-based prose from a structured analytical
result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def _is_number(value) -> bool:
    """True when a value is a usable finite number."""
    if value is None:
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _fmt_count(value) -> str:
    return f"{float(value):,.0f}"


def _fmt_pct(value, places: int = 1) -> str:
    return f"{float(value):.{places}f}%"


def _fmt_signed_pct(value, places: int = 1) -> str:
    return f"{float(value):+.{places}f}%"


def _fmt_points(value, places: int = 1) -> str:
    return f"{float(value):+.{places}f} percentage points"


@dataclass
class Briefing:
    """A structured executive brief plus the flat text rendering."""

    headline: str
    priority_band: str
    priority_score: float | None
    sections: list[dict] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    generated_by: str = "deterministic_rules"

    def as_text(self) -> str:
        parts = [self.headline, ""]
        for section in self.sections:
            parts.append(f"{section['title']}")
            parts.append(section["body"])
            parts.append("")
        return "\n".join(parts).strip()


_BAND_TONE = {
    "CRITICAL": "sustained and severe waiting-list pressure",
    "HIGH": "sustained waiting-list pressure",
    "MODERATE": "moderate waiting-list pressure",
    "LOW": "comparatively contained waiting-list pressure",
    "UNSCORED": "insufficient data for a pressure assessment",
}


def build_service_briefing(
    row: pd.Series | dict,
    provider_name: str,
    specialty_name: str,
    scenario_summary: dict | None = None,
) -> Briefing:
    """Generate an executive brief for one provider x specialty."""
    data = dict(row)
    band = str(data.get("priority_band") or "UNSCORED")
    score = data.get("priority_score")

    headline = (
        f"{specialty_name} at {provider_name} shows "
        f"{_BAND_TONE.get(band, 'an unclassified position')}."
    )

    sections: list[dict] = []

    # --- Current position -------------------------------------------------
    waiting = data.get("total_incomplete_pathways")
    if _is_number(waiting):
        body = (
            f"The service has {_fmt_count(waiting)} incomplete pathways in the "
            f"latest reporting month"
        )
        median = data.get("median_wait_weeks")
        if _is_number(median):
            body += f", with a median wait of {float(median):.1f} weeks"
        body += "."
        sections.append({"title": "Current position", "body": body})

    # --- Trend ------------------------------------------------------------
    trend_parts: list[str] = []
    growth_3m = data.get("backlog_growth_3m_pct")
    if _is_number(growth_3m):
        direction = "increased" if float(growth_3m) >= 0 else "decreased"
        trend_parts.append(
            f"The waiting list has {direction} by "
            f"{abs(float(growth_3m)):.1f}% over three months"
        )
    run = data.get("months_backlog_rising")
    if _is_number(run) and float(run) >= 2:
        trend_parts.append(
            f"and has risen in {int(float(run))} consecutive reporting months"
        )
    if trend_parts:
        sections.append(
            {"title": "Trend", "body": " ".join(trend_parts).strip() + "."}
        )

    # --- Performance ------------------------------------------------------
    within = data.get("pct_within_18_weeks")
    if _is_number(within):
        body = f"{_fmt_pct(within)} of pathways are within 18 weeks"
        change = data.get("pct_within_18_weeks_change_3m")
        if _is_number(change):
            movement = "improved" if float(change) >= 0 else "deteriorated"
            body += (
                f", having {movement} by "
                f"{abs(float(change)):.1f} percentage points over three months"
            )
        long_wait = data.get("pct_over_52_weeks")
        if _is_number(long_wait) and float(long_wait) > 0:
            body += (
                f". {_fmt_pct(long_wait, 2)} of the list has been waiting "
                "beyond 52 weeks"
            )
        sections.append({"title": "Performance", "body": body + "."})

    # --- Activity ---------------------------------------------------------
    activity = data.get("rolling_activity_3m")
    if _is_number(activity) and float(activity) > 0:
        body = (
            f"Recent completed activity averages {_fmt_count(activity)} "
            "pathways per month"
        )
        months_to_clear = data.get("months_to_clear_at_current_activity")
        if _is_number(months_to_clear):
            body += (
                f", equivalent to {float(months_to_clear):.1f} months of "
                "activity to clear the current list at that rate"
            )
        activity_change = data.get("activity_change_3m_pct")
        if _is_number(activity_change):
            body += (
                f". Activity has changed by {_fmt_signed_pct(activity_change)} "
                "over three months"
            )
        sections.append({"title": "Activity", "body": body + "."})

    # --- Outlook ----------------------------------------------------------
    status = data.get("forecast_status")
    if status == "ok":
        forecast_3m = data.get("forecast_3m")
        change_3m = data.get("forecast_change_3m_pct")
        if _is_number(forecast_3m) and _is_number(change_3m):
            direction = "further growth" if float(change_3m) >= 0 else "a reduction"
            body = (
                f"The selected forecast model projects {direction} of "
                f"{abs(float(change_3m)):.1f}% over three months, to "
                f"approximately {_fmt_count(forecast_3m)} pathways"
            )
            confidence = data.get("forecast_confidence")
            model = data.get("forecast_model")
            if confidence:
                body += (
                    f". Forecast confidence is rated {str(confidence).lower()}"
                )
                if model:
                    body += f" using a {str(model).replace('_', ' ')} model"
            sections.append({"title": "Outlook", "body": body + "."})
    else:
        message = data.get("forecast_message") or (
            "There is insufficient history to produce a forecast for this "
            "service."
        )
        sections.append({"title": "Outlook", "body": str(message)})

    # --- Scenario ---------------------------------------------------------
    if scenario_summary and scenario_summary.get("status") == "ok":
        uplift = scenario_summary.get("uplift_pct")
        difference = scenario_summary.get("difference_from_baseline")
        if _is_number(uplift) and _is_number(difference):
            body = (
                f"Under an illustrative {float(uplift):.0f}% activity uplift, "
                f"the modelled three-month waiting list is "
                f"{abs(float(difference)):,.0f} pathways "
                f"{'lower' if float(difference) < 0 else 'higher'} than "
                "baseline"
            )
            required = scenario_summary.get("uplift_required_to_stabilise_pct")
            if _is_number(required) and float(required) > 0:
                body += (
                    f". Holding the list at its current level over three months "
                    f"would require an activity uplift of approximately "
                    f"{float(required):.1f}%"
                )
            elif _is_number(required) and float(required) == 0:
                body += (
                    ". The baseline projection does not indicate growth, so no "
                    "uplift is implied to stabilise the list"
                )
            sections.append(
                {"title": "Illustrative scenario", "body": body + "."}
            )

    # --- Priority ---------------------------------------------------------
    if _is_number(score):
        sections.append(
            {
                "title": "Priority",
                "body": (
                    f"{band} - priority score {float(score):.0f} out of 100. "
                    + _recommendation(band)
                ),
            }
        )

    return Briefing(
        headline=headline,
        priority_band=band,
        priority_score=float(score) if _is_number(score) else None,
        sections=sections,
        drivers=build_drivers(data),
        recommended_actions=_actions(band, data),
        caveats=[
            "Derived from aggregate public NHS England statistics; no "
            "patient-level information is used.",
            "Forecasts extrapolate recent behaviour and carry material "
            "uncertainty.",
            "Scenario figures are modelled estimates, not predicted outcomes, "
            "and imply no causal relationship.",
        ],
    )


def _recommendation(band: str) -> str:
    return {
        "CRITICAL": (
            "Immediate operational review is recommended, covering waiting-list "
            "validation, activity constraints and specialty-level capacity."
        ),
        "HIGH": (
            "Operational review should prioritise validation of pathway data, "
            "activity constraints and specialty-level capacity."
        ),
        "MODERATE": (
            "Continued monitoring is recommended, with review if the current "
            "trajectory persists for a further reporting period."
        ),
        "LOW": (
            "No specific escalation is indicated on these measures; routine "
            "monitoring is sufficient."
        ),
    }.get(band, "The available data does not support a prioritisation judgement.")


def _actions(band: str, data: dict) -> list[str]:
    """Concrete next steps implied by which components drove the score."""
    actions: list[str] = []
    if band in {"CRITICAL", "HIGH"}:
        actions.append(
            "Validate the waiting list to confirm the recorded position is "
            "accurate before drawing operational conclusions."
        )
    growth = data.get("backlog_growth_3m_pct")
    if _is_number(growth) and float(growth) > 5:
        actions.append(
            "Review whether recent additions to the list are outpacing "
            "completed activity, and identify the specialties driving it."
        )
    long_wait = data.get("pct_over_52_weeks")
    if _is_number(long_wait) and float(long_wait) > 1:
        actions.append(
            "Review the longest-waiting cohort and confirm each pathway has a "
            "planned next step."
        )
    within = data.get("pct_within_18_weeks")
    if _is_number(within) and float(within) < 60:
        actions.append(
            "Assess capacity against demand for this treatment function, "
            "including theatre, outpatient and diagnostic constraints."
        )
    persistence = data.get("months_backlog_rising")
    if _is_number(persistence) and float(persistence) >= 4:
        actions.append(
            "Treat this as a structural rather than transient position: "
            f"the list has grown for {int(float(persistence))} consecutive "
            "months."
        )
    if not actions:
        actions.append(
            "Maintain routine monitoring; no specific escalation is indicated "
            "on the measures available."
        )
    return actions


def build_drivers(row: pd.Series | dict) -> list[str]:
    """Bullet points explaining why a service scored as it did.

    Ordered by the size of each component's contribution, so the first bullet
    is always the largest single reason.
    """
    data = dict(row)
    from app.analytics.priority import COMPONENTS

    ranked = sorted(
        COMPONENTS,
        key=lambda c: float(data.get(f"contribution_{c.key}") or 0.0),
        reverse=True,
    )

    drivers: list[str] = []
    for component in ranked:
        score = data.get(f"score_{component.key}")
        if not _is_number(score):
            continue
        score = float(score)
        detail = _driver_detail(component.key, data)
        if score >= 50 or detail:
            drivers.append(
                f"{component.label}: {score:.0f}/100"
                + (f" - {detail}" if detail else "")
            )
    return drivers[:5]


def _driver_detail(key: str, data: dict) -> str:
    """The concrete number behind a component score."""
    if key == "backlog_pressure":
        growth = data.get("backlog_growth_3m_pct")
        if _is_number(growth):
            return f"waiting list {_fmt_signed_pct(growth)} over three months"
    elif key == "long_wait_burden":
        over_52 = data.get("pct_over_52_weeks")
        if _is_number(over_52):
            return f"{_fmt_pct(over_52, 2)} of the list beyond 52 weeks"
        over_18 = data.get("pct_over_18_weeks")
        if _is_number(over_18):
            return f"{_fmt_pct(over_18)} of the list beyond 18 weeks"
    elif key == "performance_gap":
        within = data.get("pct_within_18_weeks")
        if _is_number(within):
            detail = f"{_fmt_pct(within)} within 18 weeks"
            change = data.get("pct_within_18_weeks_change_3m")
            if _is_number(change):
                detail += f", {_fmt_points(change)} over three months"
            return detail
    elif key == "forecast_risk":
        if data.get("forecast_status") == "ok":
            change = data.get("forecast_change_3m_pct")
            if _is_number(change):
                return f"three-month forecast {_fmt_signed_pct(change)}"
        return "no forecast available; scored neutrally"
    elif key == "persistence":
        run = data.get("months_backlog_rising")
        if _is_number(run) and float(run) > 0:
            return (
                f"list has risen in {int(float(run))} consecutive reporting "
                "months"
            )
        share = data.get("share_months_rising_6m")
        if _is_number(share):
            return f"list grew in {_fmt_pct(share, 0)} of the last six months"
    return ""


def build_attention_cards(ranked: pd.DataFrame, limit: int = 5) -> list[dict]:
    """Compact "what needs attention" cards for the main dashboard."""
    cards: list[dict] = []
    for position, (_, row) in enumerate(ranked.head(limit).iterrows(), start=1):
        reasons: list[str] = []
        growth = row.get("backlog_growth_3m_pct")
        if _is_number(growth):
            reasons.append(f"Backlog {_fmt_signed_pct(growth)} over 3 months")
        within = row.get("pct_within_18_weeks")
        if _is_number(within):
            reasons.append(f"{_fmt_pct(within)} within 18 weeks")
        if row.get("forecast_status") == "ok":
            change = row.get("forecast_change_3m_pct")
            if _is_number(change):
                reasons.append(f"Forecast {_fmt_signed_pct(change)} over 3 months")
        run = row.get("months_backlog_rising")
        if _is_number(run) and float(run) >= 3:
            reasons.append(f"Rising for {int(float(run))} consecutive months")

        cards.append(
            {
                "rank": position,
                "provider_code": row.get("provider_code"),
                "provider_name": row.get("provider_name"),
                "specialty_code": row.get("specialty_code"),
                "specialty_name": row.get("specialty_name"),
                "priority_score": _safe_float(row.get("priority_score")),
                "priority_band": row.get("priority_band"),
                "waiting_list": _safe_float(row.get("total_incomplete_pathways")),
                "reasons": reasons[:4],
            }
        )
    return cards


def _safe_float(value):
    return float(value) if _is_number(value) else None
