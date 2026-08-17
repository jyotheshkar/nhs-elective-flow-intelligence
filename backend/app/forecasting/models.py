"""Interpretable short-horizon forecasting models.

Deliberately simple and explainable. Provider x specialty waiting-list series
have 12-24 monthly observations - far too few for anything elaborate, and the
audience needs to be able to challenge the method in an operational meeting.

Every model exposes the same interface so ``engine.py`` can select between them
on out-of-sample error rather than on preference.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ForecastOutput:
    """Point forecasts plus a symmetric prediction interval."""

    model: str
    point: list[float]
    lower: list[float]
    upper: list[float]
    residual_sigma: float
    parameters: dict[str, float]


class ForecastModel(Protocol):
    """Interface implemented by every candidate model."""

    name: str

    def fit_predict(self, values: np.ndarray, horizon: int) -> ForecastOutput:
        ...


def _interval(
    point: np.ndarray, sigma: float, horizon: int, z: float = 1.28
) -> tuple[list[float], list[float]]:
    """Widen the interval with the square root of the horizon.

    z = 1.28 gives a nominal 80% interval. An 80% band is used rather than 95%
    because with 12-24 observations a 95% band on these series is so wide it
    stops being decision-useful, and the honest statement is "this is an
    indicative range", not "this is a rigorous confidence interval".
    """
    if not np.isfinite(sigma) or sigma <= 0:
        sigma = max(float(np.abs(point).mean()) * 0.05, 1.0)
    steps = np.arange(1, horizon + 1, dtype="float64")
    width = z * sigma * np.sqrt(steps)
    lower = np.maximum(point - width, 0.0)
    upper = point + width
    return [float(v) for v in lower], [float(v) for v in upper]


class NaiveDriftModel:
    """Last value carried forward plus the average historical drift.

    The benchmark every other model must beat. For waiting lists that move
    slowly and monotonically, it is genuinely hard to beat.
    """

    name = "naive_drift"

    def fit_predict(self, values: np.ndarray, horizon: int) -> ForecastOutput:
        n = len(values)
        last = float(values[-1])
        drift = float((values[-1] - values[0]) / (n - 1)) if n > 1 else 0.0
        point = last + drift * np.arange(1, horizon + 1, dtype="float64")
        fitted = np.concatenate([[values[0]], values[:-1] + drift])
        sigma = float(np.std(values - fitted, ddof=1)) if n > 2 else 0.0
        lower, upper = _interval(point, sigma, horizon)
        return ForecastOutput(
            model=self.name,
            point=[float(max(v, 0.0)) for v in point],
            lower=lower,
            upper=upper,
            residual_sigma=sigma,
            parameters={"drift": drift, "last_value": last},
        )


class LinearTrendModel:
    """Ordinary least squares on a time index.

    Fits the level and slope of the whole observed window. Steadier than drift
    when the series is noisy, but slower to react to a recent turning point.
    """

    name = "linear_trend"

    def __init__(self, window: int | None = None) -> None:
        self.window = window

    def fit_predict(self, values: np.ndarray, horizon: int) -> ForecastOutput:
        series = values[-self.window:] if self.window else values
        n = len(series)
        x = np.arange(n, dtype="float64")
        slope, intercept = np.polyfit(x, series, 1)
        future_x = np.arange(n, n + horizon, dtype="float64")
        point = intercept + slope * future_x
        residuals = series - (intercept + slope * x)
        sigma = float(np.std(residuals, ddof=2)) if n > 3 else float(np.std(residuals))
        lower, upper = _interval(point, sigma, horizon)
        return ForecastOutput(
            model=self.name if not self.window else f"{self.name}_{self.window}m",
            point=[float(max(v, 0.0)) for v in point],
            lower=lower,
            upper=upper,
            residual_sigma=sigma,
            parameters={"slope": float(slope), "intercept": float(intercept)},
        )


class HoltLinearModel:
    """Holt's linear (double) exponential smoothing, fitted by grid search.

    Weights recent observations more heavily than OLS, so it tracks turning
    points better. Alpha and beta are chosen by minimising in-sample one-step
    SSE over a coarse grid - adequate for 12-24 points and fully transparent.
    """

    name = "holt_linear"

    _ALPHAS = np.arange(0.1, 0.95, 0.1)
    _BETAS = np.arange(0.05, 0.65, 0.1)

    def fit_predict(self, values: np.ndarray, horizon: int) -> ForecastOutput:
        best = None
        for alpha in self._ALPHAS:
            for beta in self._BETAS:
                sse, level, trend, residuals = self._smooth(values, alpha, beta)
                if best is None or sse < best[0]:
                    best = (sse, alpha, beta, level, trend, residuals)
        assert best is not None
        _sse, alpha, beta, level, trend, residuals = best
        point = level + trend * np.arange(1, horizon + 1, dtype="float64")
        sigma = (
            float(np.std(residuals, ddof=1)) if len(residuals) > 2 else 0.0
        )
        lower, upper = _interval(point, sigma, horizon)
        return ForecastOutput(
            model=self.name,
            point=[float(max(v, 0.0)) for v in point],
            lower=lower,
            upper=upper,
            residual_sigma=sigma,
            parameters={
                "alpha": float(alpha),
                "beta": float(beta),
                "level": float(level),
                "trend": float(trend),
            },
        )

    @staticmethod
    def _smooth(
        values: np.ndarray, alpha: float, beta: float
    ) -> tuple[float, float, float, np.ndarray]:
        level = float(values[0])
        trend = float(values[1] - values[0]) if len(values) > 1 else 0.0
        residuals: list[float] = []
        for actual in values[1:]:
            forecast = level + trend
            residuals.append(float(actual - forecast))
            previous_level = level
            level = alpha * actual + (1 - alpha) * forecast
            trend = beta * (level - previous_level) + (1 - beta) * trend
        errors = np.asarray(residuals, dtype="float64")
        return float(np.sum(errors**2)), level, trend, errors


class DampedTrendModel:
    """Holt's method with a damping parameter on the trend.

    Waiting-list growth rarely continues linearly for six months. Damping pulls
    longer horizons back towards the current level, which is usually the more
    defensible operational assumption.
    """

    name = "damped_trend"

    _PHIS = (0.75, 0.85, 0.95)

    def fit_predict(self, values: np.ndarray, horizon: int) -> ForecastOutput:
        holt = HoltLinearModel()
        best = None
        for phi in self._PHIS:
            for alpha in HoltLinearModel._ALPHAS:
                for beta in HoltLinearModel._BETAS:
                    sse, level, trend, residuals = holt._smooth(values, alpha, beta)
                    if best is None or sse < best[0]:
                        best = (sse, alpha, beta, phi, level, trend, residuals)
        assert best is not None
        _sse, alpha, beta, phi, level, trend, residuals = best
        damping = np.cumsum([phi**h for h in range(1, horizon + 1)])
        point = level + trend * damping
        sigma = float(np.std(residuals, ddof=1)) if len(residuals) > 2 else 0.0
        lower, upper = _interval(point, sigma, horizon)
        return ForecastOutput(
            model=self.name,
            point=[float(max(v, 0.0)) for v in point],
            lower=lower,
            upper=upper,
            residual_sigma=sigma,
            parameters={
                "alpha": float(alpha),
                "beta": float(beta),
                "phi": float(phi),
                "level": float(level),
                "trend": float(trend),
            },
        )


def candidate_models(history_length: int) -> list[ForecastModel]:
    """Candidate models appropriate to the amount of history available."""
    models: list[ForecastModel] = [NaiveDriftModel(), LinearTrendModel()]
    if history_length >= 8:
        models.append(LinearTrendModel(window=6))
        models.append(HoltLinearModel())
    if history_length >= 10:
        models.append(DampedTrendModel())
    return models


MODEL_REGISTRY: dict[str, Callable[[], ForecastModel]] = {
    "naive_drift": NaiveDriftModel,
    "linear_trend": LinearTrendModel,
    "holt_linear": HoltLinearModel,
    "damped_trend": DampedTrendModel,
}


def clean_series(values: pd.Series) -> np.ndarray:
    """Return a contiguous float array, dropping leading/trailing gaps.

    Interior gaps are linearly interpolated: a single missing month in an
    otherwise complete series should not disqualify it from forecasting, but
    the interpolation is limited so long gaps still fail the history check.
    """
    series = pd.Series(values, dtype="float64").interpolate(limit=2, limit_area="inside")
    series = series.dropna()
    return series.to_numpy(dtype="float64")
