"""Numeric helpers used across the analytics layer.

These are deliberately small, pure and individually testable. Division by zero
and empty windows are pervasive in sparse NHS provider x specialty series, so
every helper here returns NaN rather than raising or silently producing inf.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def safe_divide(
    numerator: pd.Series | np.ndarray | float,
    denominator: pd.Series | np.ndarray | float,
    fill: float = np.nan,
) -> pd.Series | np.ndarray | float:
    """Element-wise division that yields ``fill`` wherever the denominator is
    zero, missing, or the result is non-finite.

    Naive division on NHS provider data produces ``inf`` whenever a specialty
    appears for the first time (previous month = 0), which then poisons every
    downstream percentile. Returning NaN keeps those rows excludable.
    """
    if isinstance(numerator, pd.Series) or isinstance(denominator, pd.Series):
        num = pd.Series(numerator) if not isinstance(numerator, pd.Series) else numerator
        den = pd.Series(denominator) if not isinstance(denominator, pd.Series) else denominator
        with np.errstate(divide="ignore", invalid="ignore"):
            result = num.astype("float64") / den.astype("float64")
        return result.replace([np.inf, -np.inf], np.nan).fillna(fill)

    with np.errstate(divide="ignore", invalid="ignore"):
        result = np.divide(
            np.asarray(numerator, dtype="float64"),
            np.asarray(denominator, dtype="float64"),
        )
    result = np.where(np.isfinite(result), result, fill)
    return float(result) if np.ndim(result) == 0 else result


def percentile_rank(series: pd.Series) -> pd.Series:
    """Cross-sectional percentile rank scaled to 0-100.

    Preferred over min-max scaling for the priority score: a single provider
    with an extreme value would otherwise compress every other organisation
    into the bottom of the range. NaNs stay NaN.
    """
    valid = series.notna()
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    if valid.sum() == 0:
        return out
    if valid.sum() == 1:
        out.loc[valid] = 50.0
        return out
    out.loc[valid] = series[valid].rank(pct=True, method="average") * 100.0
    return out


def clipped_robust_scale(
    series: pd.Series,
    lower_quantile: float = 0.05,
    upper_quantile: float = 0.95,
) -> pd.Series:
    """Scale to 0-100 between robust quantile bounds, clipping the tails.

    Used where the *magnitude* of a metric matters rather than only its rank
    (e.g. the 18-week gap, where a 40-point shortfall is materially worse than
    a 20-point one even if both sit in the same percentile bucket).
    """
    valid = series.dropna()
    out = pd.Series(np.nan, index=series.index, dtype="float64")
    if valid.empty:
        return out
    lo = float(valid.quantile(lower_quantile))
    hi = float(valid.quantile(upper_quantile))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        out.loc[series.notna()] = 50.0
        return out
    scaled = (series - lo) / (hi - lo) * 100.0
    return scaled.clip(lower=0.0, upper=100.0)


def linear_trend_slope(values: pd.Series | np.ndarray) -> float:
    """Ordinary-least-squares slope of ``values`` against 0..n-1.

    Returns NaN for fewer than two finite observations. Units are "units per
    month" because the series is monthly and evenly spaced.
    """
    arr = np.asarray(pd.Series(values).astype("float64").to_numpy())
    mask = np.isfinite(arr)
    if mask.sum() < 2:
        return float("nan")
    y = arr[mask]
    x = np.arange(len(arr), dtype="float64")[mask]
    if np.allclose(x, x[0]):
        return float("nan")
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def robust_zscore(values: pd.Series) -> pd.Series:
    """Median/MAD-based z-score, resistant to the outliers it is detecting.

    Uses the 1.4826 consistency constant so the result is comparable to a
    standard z-score under normality. Falls back to NaN when the MAD is zero
    (a perfectly flat series has no meaningful outliers).
    """
    valid = values.dropna()
    if len(valid) < 3:
        return pd.Series(np.nan, index=values.index, dtype="float64")
    median = float(valid.median())
    mad = float((valid - median).abs().median())
    if mad == 0:
        return pd.Series(np.nan, index=values.index, dtype="float64")
    return (values - median) / (1.4826 * mad)


def pct_change_over(series: pd.Series, periods: int) -> pd.Series:
    """Percentage change against the value ``periods`` rows earlier, as a
    percentage (not a fraction), NaN-safe against zero baselines."""
    previous = series.shift(periods)
    return safe_divide(series - previous, previous) * 100.0


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a scalar to [low, high], passing NaN through unchanged."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return float("nan")
    return float(min(max(value, low), high))
