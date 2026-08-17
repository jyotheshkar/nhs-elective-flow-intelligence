"""Longitudinal metric derivation on the canonical fact table.

Every metric here is computed *within* a provider x specialty series ordered by
reporting month. Cross-sectional comparisons (percentiles, benchmarks) belong in
``benchmarks.py``; scoring belongs in ``priority.py``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.utils.logging import get_logger
from app.utils.mathx import linear_trend_slope, pct_change_over, safe_divide

logger = get_logger(__name__)

SERIES_KEYS = ["provider_code", "specialty_code"]


def _rolling_slope(series: pd.Series, window: int) -> pd.Series:
    """Rolling OLS slope over the trailing ``window`` observations."""
    return series.rolling(window=window, min_periods=window).apply(
        linear_trend_slope, raw=False
    )


def add_trend_metrics(fact: pd.DataFrame) -> pd.DataFrame:
    """Add change, growth, rolling, trend and volatility metrics.

    Returns a copy of ``fact`` with additional columns. Rows are sorted by
    series and month, which every ``shift``/``rolling`` below depends on.
    """
    if fact.empty:
        return fact.copy()

    df = fact.sort_values([*SERIES_KEYS, "reporting_month"]).copy()
    grouped = df.groupby(SERIES_KEYS, sort=False, group_keys=False)
    waiting = df["total_incomplete_pathways"]

    # --- Absolute and percentage movement --------------------------------
    df["waiting_list_prev_month"] = grouped["total_incomplete_pathways"].shift(1)
    df["backlog_change_1m"] = waiting - df["waiting_list_prev_month"]
    df["backlog_growth_1m_pct"] = grouped["total_incomplete_pathways"].transform(
        lambda s: pct_change_over(s, 1)
    )
    df["backlog_growth_3m_pct"] = grouped["total_incomplete_pathways"].transform(
        lambda s: pct_change_over(s, 3)
    )
    df["backlog_growth_6m_pct"] = grouped["total_incomplete_pathways"].transform(
        lambda s: pct_change_over(s, 6)
    )
    df["backlog_change_3m"] = waiting - grouped["total_incomplete_pathways"].shift(3)
    df["backlog_change_6m"] = waiting - grouped["total_incomplete_pathways"].shift(6)

    # --- Smoothing --------------------------------------------------------
    df["waiting_list_rolling_3m"] = grouped["total_incomplete_pathways"].transform(
        lambda s: s.rolling(3, min_periods=2).mean()
    )
    df["waiting_list_rolling_6m"] = grouped["total_incomplete_pathways"].transform(
        lambda s: s.rolling(6, min_periods=3).mean()
    )

    # --- Trend slopes (pathways per month) --------------------------------
    df["trend_slope_3m"] = grouped["total_incomplete_pathways"].transform(
        lambda s: _rolling_slope(s, 3)
    )
    df["trend_slope_6m"] = grouped["total_incomplete_pathways"].transform(
        lambda s: _rolling_slope(s, 6)
    )
    # Slope normalised by list size, so a 200-pathway monthly rise means
    # something different for a 500-strong list than for a 50,000-strong one.
    df["trend_slope_6m_pct_of_list"] = safe_divide(df["trend_slope_6m"], waiting) * 100.0

    # --- Volatility -------------------------------------------------------
    df["backlog_change_volatility_6m"] = grouped["backlog_change_1m"].transform(
        lambda s: s.rolling(6, min_periods=3).std()
    )

    # --- 18-week performance movement -------------------------------------
    df["pct_within_18_weeks_prev"] = grouped["pct_within_18_weeks"].shift(1)
    df["pct_within_18_weeks_change_1m"] = (
        df["pct_within_18_weeks"] - df["pct_within_18_weeks_prev"]
    )
    df["pct_within_18_weeks_change_3m"] = df["pct_within_18_weeks"] - grouped[
        "pct_within_18_weeks"
    ].shift(3)

    # --- Persistence: consecutive months of deterioration -----------------
    df["months_backlog_rising"] = grouped["backlog_change_1m"].transform(
        _consecutive_positive
    )
    df["months_performance_falling"] = grouped[
        "pct_within_18_weeks_change_1m"
    ].transform(_consecutive_negative)
    # Share of the last 6 months in which the list grew - a smoother
    # persistence signal than the raw consecutive run.
    df["share_months_rising_6m"] = grouped["backlog_change_1m"].transform(
        lambda s: (s > 0).rolling(6, min_periods=3).mean() * 100.0
    )

    # --- Activity ---------------------------------------------------------
    df["activity_prev_month"] = grouped["completed_pathways"].shift(1)
    df["activity_change_1m_pct"] = grouped["completed_pathways"].transform(
        lambda s: pct_change_over(s, 1)
    )
    df["activity_change_3m_pct"] = grouped["completed_pathways"].transform(
        lambda s: pct_change_over(s, 3)
    )
    df["rolling_activity_3m"] = grouped["completed_pathways"].transform(
        lambda s: s.rolling(3, min_periods=2).mean()
    )

    # Months of activity required to clear the current list at recent rates.
    # A capacity-relative measure of list size; null where activity is missing.
    df["months_to_clear_at_current_activity"] = safe_divide(
        waiting, df["rolling_activity_3m"]
    )

    # Implied net flow: the additions to the list that must have occurred to
    # move the backlog by the observed amount given observed completions.
    #
    #   implied_additions = backlog_change + completed_pathways
    #
    # This is an accounting identity, NOT observed referrals. NHS England does
    # not publish referrals at this grain, so it is labelled "implied" wherever
    # it surfaces in the product.
    df["implied_additions"] = df["backlog_change_1m"] + df["completed_pathways"]
    df["rolling_implied_additions_3m"] = grouped["implied_additions"].transform(
        lambda s: s.rolling(3, min_periods=2).mean()
    )

    # Pressure indicator: backlog growing faster than activity.
    df["activity_gap_pct"] = (
        df["backlog_growth_3m_pct"] - df["activity_change_3m_pct"]
    )

    return df.reset_index(drop=True)


def _consecutive_positive(series: pd.Series) -> pd.Series:
    """Length of the run of strictly positive values ending at each row."""
    return _consecutive_run(series > 0, series.notna())


def _consecutive_negative(series: pd.Series) -> pd.Series:
    """Length of the run of strictly negative values ending at each row."""
    return _consecutive_run(series < 0, series.notna())


def _consecutive_run(condition: pd.Series, valid: pd.Series) -> pd.Series:
    """Count consecutive True values, resetting on False and on missing data."""
    counts: list[float] = []
    run = 0
    for is_true, is_valid in zip(condition.to_numpy(), valid.to_numpy(), strict=False):
        if not is_valid:
            run = 0
            counts.append(np.nan)
            continue
        run = run + 1 if is_true else 0
        counts.append(float(run))
    return pd.Series(counts, index=condition.index, dtype="float64")


def latest_snapshot(metrics: pd.DataFrame) -> pd.DataFrame:
    """The most recent reporting month for every provider x specialty series."""
    if metrics.empty:
        return metrics.copy()
    latest_month = metrics["reporting_month"].max()
    return metrics[metrics["reporting_month"] == latest_month].reset_index(drop=True)


def series_history(
    metrics: pd.DataFrame, provider_code: str, specialty_code: str
) -> pd.DataFrame:
    """The full monthly history for one provider x specialty."""
    mask = (metrics["provider_code"] == provider_code) & (
        metrics["specialty_code"] == specialty_code
    )
    return metrics[mask].sort_values("reporting_month").reset_index(drop=True)
