"""Executive KPI construction.

Each KPI carries its own definition, source and calculation so the UI tooltip is
generated from the same object that produced the number - the explanation can
never drift from the metric.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import get_settings
from app.models.schemas import KpiCard

_SOURCE = "NHS England Consultant-led RTT Waiting Times (provider level)"


def _finite(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _direction(value: float | None) -> str:
    if value is None:
        return "none"
    if value > 0.05:
        return "up"
    if value < -0.05:
        return "down"
    return "flat"


def _fmt_count(value: float | None) -> str:
    return f"{value:,.0f}" if value is not None else "-"


def _fmt_pct(value: float | None, places: int = 1) -> str:
    return f"{value:.{places}f}%" if value is not None else "-"


def _fmt_signed(value: float | None, places: int = 1, suffix: str = "") -> str:
    return f"{value:+,.{places}f}{suffix}" if value is not None else "-"


def build_kpis(
    snapshot: pd.DataFrame,
    national_trend: pd.DataFrame,
    quality_score: float | None,
) -> list[KpiCard]:
    """Build the executive KPI row for the filtered selection."""
    settings = get_settings()
    cards: list[KpiCard] = []

    waiting = _finite(snapshot["total_incomplete_pathways"].sum())
    within = _finite(snapshot["within_18_weeks"].sum())
    over_52 = _finite(snapshot.get("over_52_weeks", pd.Series(dtype=float)).sum())

    # Month-on-month movement, summed across the current selection.
    previous_waiting = None
    if "backlog_change_1m" in snapshot.columns and waiting is not None:
        change = _finite(snapshot["backlog_change_1m"].sum())
        if change is not None:
            previous_waiting = waiting - change

    mom_change = (
        waiting - previous_waiting
        if waiting is not None and previous_waiting is not None
        else None
    )
    mom_pct = (
        (mom_change / previous_waiting * 100.0)
        if mom_change is not None and previous_waiting
        else None
    )

    cards.append(
        KpiCard(
            key="waiting_list",
            label="Total waiting list",
            value=waiting,
            display_value=_fmt_count(waiting),
            unit="pathways",
            secondary_label="Month on month",
            secondary_value=mom_pct,
            secondary_display=(
                f"{_fmt_signed(mom_change, 0)} ({_fmt_signed(mom_pct, 1, '%')})"
                if mom_change is not None
                else "-"
            ),
            direction=_direction(mom_pct),
            higher_is_better=False,
            definition=(
                "Total incomplete RTT pathways: patients waiting to start "
                "consultant-led treatment in the current selection."
            ),
            source=_SOURCE,
            calculation=(
                "SUM(total incomplete pathways) across the selected provider x "
                "specialty rows in the latest reporting month."
            ),
        )
    )

    pct_within = (within / waiting * 100.0) if waiting else None

    # Weighted month-on-month change, recomputed from summed counts rather than
    # averaging per-service percentages.
    #
    # Both sides are restricted to services that actually reported a previous
    # month. Including a new service's current list in the denominator while it
    # contributes nothing to the numerator would understate the prior position
    # and overstate the improvement.
    previous_pct = None
    pct_change = None
    required = {
        "within_18_weeks", "pct_within_18_weeks_prev",
        "total_incomplete_pathways", "backlog_change_1m",
    }
    if required <= set(snapshot.columns):
        comparable = snapshot[
            snapshot["pct_within_18_weeks_prev"].notna()
            & snapshot["backlog_change_1m"].notna()
        ]
        if not comparable.empty:
            previous_total = (
                comparable["total_incomplete_pathways"]
                - comparable["backlog_change_1m"]
            )
            previous_within_sum = _finite(
                (comparable["pct_within_18_weeks_prev"] / 100.0 * previous_total).sum()
            )
            previous_total_sum = _finite(previous_total.sum())
            current_within_sum = _finite(comparable["within_18_weeks"].sum())
            current_total_sum = _finite(comparable["total_incomplete_pathways"].sum())

            if (
                previous_within_sum is not None
                and previous_total_sum
                and current_within_sum is not None
                and current_total_sum
            ):
                previous_pct = previous_within_sum / previous_total_sum * 100.0
                current_pct_comparable = (
                    current_within_sum / current_total_sum * 100.0
                )
                pct_change = current_pct_comparable - previous_pct

    cards.append(
        KpiCard(
            key="within_18_weeks",
            label="Within 18 weeks",
            value=pct_within,
            display_value=_fmt_pct(pct_within),
            unit="%",
            secondary_label="vs previous month",
            secondary_value=pct_change,
            secondary_display=(
                f"{_fmt_signed(pct_change, 1)} pp" if pct_change is not None else "-"
            ),
            direction=_direction(pct_change),
            higher_is_better=True,
            definition=(
                "Share of incomplete pathways waiting less than 18 weeks. The "
                f"operational benchmark used in this product is "
                f"{settings.referral_to_treatment_benchmark:.0f}%."
            ),
            source=_SOURCE,
            calculation=(
                "SUM(within 18 weeks) / SUM(total incomplete pathways) x 100, "
                "weighted by list size rather than averaged across services."
            ),
        )
    )

    pct_over_52 = (over_52 / waiting * 100.0) if waiting and over_52 is not None else None
    cards.append(
        KpiCard(
            key="long_wait_burden",
            label="Waiting 52+ weeks",
            value=over_52,
            display_value=_fmt_count(over_52),
            unit="pathways",
            secondary_label="Share of list",
            secondary_value=pct_over_52,
            secondary_display=_fmt_pct(pct_over_52, 2),
            direction="none",
            higher_is_better=False,
            definition=(
                "Pathways where the patient has been waiting more than 52 "
                "weeks. This is the longest-wait band published consistently "
                "across the loaded period."
            ),
            source=_SOURCE,
            calculation="SUM(total 52 plus weeks) across the selection.",
        )
    )

    highest = None
    if "priority_score" in snapshot.columns and not snapshot.empty:
        rankable = snapshot[snapshot.get("is_rankable", True)]
        basis = rankable if not rankable.empty else snapshot
        by_specialty = (
            basis.groupby("specialty_name")["priority_score"].mean().sort_values()
        )
        if not by_specialty.empty:
            highest = (by_specialty.index[-1], float(by_specialty.iloc[-1]))

    cards.append(
        KpiCard(
            key="highest_pressure_specialty",
            label="Highest pressure specialty",
            value=highest[1] if highest else None,
            display_value=highest[0] if highest else "-",
            unit="specialty",
            secondary_label="Mean priority score",
            secondary_value=highest[1] if highest else None,
            secondary_display=(
                f"{highest[1]:.0f}/100" if highest else "-"
            ),
            direction="none",
            higher_is_better=False,
            definition=(
                "Treatment function with the highest mean operational priority "
                "score across the selected providers."
            ),
            source="Derived - see the Methodology page for the score formula.",
            calculation=(
                "AVG(priority score) grouped by treatment function, restricted "
                "to services above the ranking threshold."
            ),
        )
    )

    forecast_total = None
    forecast_pct = None
    if "forecast_3m" in snapshot.columns:
        ok = snapshot[snapshot.get("forecast_status") == "ok"]
        if not ok.empty:
            forecast_total = _finite(ok["forecast_3m"].sum())
            base = _finite(ok["total_incomplete_pathways"].sum())
            if forecast_total is not None and base:
                forecast_pct = (forecast_total - base) / base * 100.0

    cards.append(
        KpiCard(
            key="forecast_3m",
            label="Forecast list (3 months)",
            value=forecast_total,
            display_value=_fmt_count(forecast_total),
            unit="pathways",
            secondary_label="Modelled change",
            secondary_value=forecast_pct,
            secondary_display=_fmt_signed(forecast_pct, 1, "%"),
            direction=_direction(forecast_pct),
            higher_is_better=False,
            definition=(
                "Sum of three-month waiting-list forecasts for services with "
                "enough history to model. Services without a forecast are "
                "excluded, so this is not directly comparable with the total "
                "waiting list."
            ),
            source="Derived - interpretable time-series models, backtested.",
            calculation=(
                "SUM(forecast at +3 months) over services where "
                "forecast_status = 'ok'."
            ),
        )
    )

    cards.append(
        KpiCard(
            key="data_quality",
            label="Data quality score",
            value=quality_score,
            display_value=(
                f"{quality_score:.0f}/100" if quality_score is not None else "-"
            ),
            unit="score",
            secondary_label="Completeness, consistency, freshness, anomalies",
            secondary_value=None,
            secondary_display=None,
            direction="none",
            higher_is_better=True,
            definition=(
                "Composite score across completeness (40%), consistency (25%), "
                "freshness (20%) and anomaly burden (15%)."
            ),
            source="Derived - see the Data Quality page for every check.",
            calculation=(
                "Weighted sum of the four dimension scores, each scaled 0-100."
            ),
        )
    )

    return cards
