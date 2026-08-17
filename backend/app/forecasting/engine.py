"""Per-series forecast generation with honest model selection.

For every provider x specialty waiting-list series:

  1. check there is enough history (otherwise return ``insufficient_history``)
  2. backtest each candidate model with a rolling origin
  3. select the model with the lowest out-of-sample MAE
  4. refit on the full series and forecast +1, +3 and +6 months
  5. attach a confidence label derived from the backtest error, not from the
     model's own in-sample fit

Selecting on out-of-sample error means the naive benchmark frequently wins, and
that is reported rather than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.config import get_settings
from app.forecasting.models import ForecastModel, candidate_models, clean_series
from app.forecasting.validation import BacktestResult, rolling_origin_backtest
from app.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_HORIZONS = (1, 3, 6)

STATUS_OK = "ok"
STATUS_INSUFFICIENT = "insufficient_history"

CONFIDENCE_HIGH = "High"
CONFIDENCE_MODERATE = "Moderate"
CONFIDENCE_LOW = "Low"
CONFIDENCE_NONE = "Insufficient data"


@dataclass
class SeriesForecast:
    """Forecast result for one provider x specialty series."""

    provider_code: str
    specialty_code: str
    status: str
    model: str | None = None
    history_months: int = 0
    last_actual: float | None = None
    last_actual_month: str | None = None
    horizons: dict[int, float] = field(default_factory=dict)
    lower: dict[int, float] = field(default_factory=dict)
    upper: dict[int, float] = field(default_factory=dict)
    forecast_months: dict[int, str] = field(default_factory=dict)
    backtest: BacktestResult | None = None
    confidence: str = CONFIDENCE_NONE
    message: str = ""

    @property
    def forecast_change_3m_pct(self) -> float:
        """Modelled percentage change in the list over three months."""
        if self.status != STATUS_OK or not self.last_actual:
            return float("nan")
        target = self.horizons.get(3)
        if target is None or self.last_actual == 0:
            return float("nan")
        return (target - self.last_actual) / self.last_actual * 100.0

    @property
    def forecast_change_6m_pct(self) -> float:
        if self.status != STATUS_OK or not self.last_actual:
            return float("nan")
        target = self.horizons.get(6)
        if target is None or self.last_actual == 0:
            return float("nan")
        return (target - self.last_actual) / self.last_actual * 100.0


def _confidence_label(backtest: BacktestResult | None, history: int) -> str:
    """Map backtest accuracy onto a plain-language confidence label.

    Thresholds are on MAPE of the one-step-ahead backtest and are documented in
    docs/methodology.md. They are judgement calls, stated as such.
    """
    if backtest is None or not np.isfinite(backtest.mape) or backtest.folds < 2:
        return CONFIDENCE_LOW if history >= 6 else CONFIDENCE_NONE
    if backtest.mape <= 3.0 and backtest.folds >= 3:
        return CONFIDENCE_HIGH
    if backtest.mape <= 8.0:
        return CONFIDENCE_MODERATE
    return CONFIDENCE_LOW


def _future_months(last_month: pd.Timestamp, horizons: tuple[int, ...]) -> dict[int, str]:
    return {
        h: (last_month + pd.DateOffset(months=h)).strftime("%Y-%m") for h in horizons
    }


def forecast_series(
    history: pd.DataFrame,
    provider_code: str,
    specialty_code: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    value_column: str = "total_incomplete_pathways",
) -> SeriesForecast:
    """Forecast one series, or explain why it cannot be forecast."""
    settings = get_settings()
    ordered = history.sort_values("reporting_month")
    values = clean_series(ordered[value_column])
    minimum = settings.min_history_for_forecast

    if len(values) < minimum:
        return SeriesForecast(
            provider_code=provider_code,
            specialty_code=specialty_code,
            status=STATUS_INSUFFICIENT,
            history_months=len(values),
            confidence=CONFIDENCE_NONE,
            message=(
                f"Only {len(values)} usable monthly observations; at least "
                f"{minimum} are required before a forecast is produced."
            ),
        )

    # A perfectly flat series breaks percentage error metrics and tells us
    # nothing; treat it as forecastable but flag low confidence via backtest.
    models: list[ForecastModel] = candidate_models(len(values))
    max_horizon = max(horizons)

    scored: list[tuple[float, ForecastModel, BacktestResult]] = []
    for model in models:
        result = rolling_origin_backtest(values, model, horizon=1)
        score = result.mae if np.isfinite(result.mae) else float("inf")
        scored.append((score, model, result))

    scored.sort(key=lambda item: item[0])
    _score, best_model, best_backtest = scored[0]

    try:
        output = best_model.fit_predict(values, max_horizon)
    except (ValueError, np.linalg.LinAlgError) as exc:
        logger.warning(
            "Forecast failed for %s/%s: %s", provider_code, specialty_code, exc
        )
        return SeriesForecast(
            provider_code=provider_code,
            specialty_code=specialty_code,
            status=STATUS_INSUFFICIENT,
            history_months=len(values),
            confidence=CONFIDENCE_NONE,
            message=f"Model fitting failed: {exc}",
        )

    last_month = pd.Timestamp(ordered["reporting_month"].max())
    return SeriesForecast(
        provider_code=provider_code,
        specialty_code=specialty_code,
        status=STATUS_OK,
        model=output.model,
        history_months=len(values),
        last_actual=float(values[-1]),
        last_actual_month=last_month.strftime("%Y-%m"),
        horizons={h: float(output.point[h - 1]) for h in horizons},
        lower={h: float(output.lower[h - 1]) for h in horizons},
        upper={h: float(output.upper[h - 1]) for h in horizons},
        forecast_months=_future_months(last_month, horizons),
        backtest=best_backtest,
        confidence=_confidence_label(best_backtest, len(values)),
    )


def forecast_all(
    metrics: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    min_latest_waiting_list: int = 0,
) -> pd.DataFrame:
    """Forecast every provider x specialty series in the fact table.

    ``min_latest_waiting_list`` skips very small series, which are numerous and
    whose forecasts are dominated by rounding noise.
    """
    if metrics.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    grouped = metrics.groupby(["provider_code", "specialty_code"], sort=False)
    total = grouped.ngroups
    logger.info("Forecasting %d provider x specialty series", total)

    for index, ((provider, specialty), history) in enumerate(grouped, start=1):
        if index % 500 == 0:
            logger.info("  forecast progress: %d/%d", index, total)

        latest_value = history.sort_values("reporting_month")[
            "total_incomplete_pathways"
        ].iloc[-1]
        if (
            min_latest_waiting_list
            and pd.notna(latest_value)
            and latest_value < min_latest_waiting_list
        ):
            result = SeriesForecast(
                provider_code=provider,
                specialty_code=specialty,
                status=STATUS_INSUFFICIENT,
                history_months=len(history),
                confidence=CONFIDENCE_NONE,
                message=(
                    f"Waiting list of {int(latest_value)} is below the "
                    f"{min_latest_waiting_list}-pathway threshold for modelling."
                ),
            )
        else:
            result = forecast_series(history, provider, specialty, horizons)
        rows.append(_to_row(result, horizons))

    frame = pd.DataFrame(rows)
    ok = int((frame["forecast_status"] == STATUS_OK).sum())
    logger.info(
        "Forecasts produced for %d/%d series (%d insufficient history)",
        ok, len(frame), len(frame) - ok,
    )
    return frame


def _to_row(result: SeriesForecast, horizons: tuple[int, ...]) -> dict:
    """Flatten a SeriesForecast into a warehouse row."""
    row: dict = {
        "provider_code": result.provider_code,
        "specialty_code": result.specialty_code,
        "forecast_status": result.status,
        "forecast_model": result.model,
        "forecast_history_months": result.history_months,
        "forecast_confidence": result.confidence,
        "forecast_message": result.message,
        "forecast_last_actual": result.last_actual,
        "forecast_change_3m_pct": result.forecast_change_3m_pct,
        "forecast_change_6m_pct": result.forecast_change_6m_pct,
    }
    for h in horizons:
        row[f"forecast_{h}m"] = result.horizons.get(h)
        row[f"forecast_{h}m_lower"] = result.lower.get(h)
        row[f"forecast_{h}m_upper"] = result.upper.get(h)
        row[f"forecast_{h}m_month"] = result.forecast_months.get(h)
    if result.backtest is not None:
        row["backtest_mae"] = result.backtest.mae
        row["backtest_rmse"] = result.backtest.rmse
        row["backtest_mape"] = result.backtest.mape
        row["backtest_folds"] = result.backtest.folds
        row["backtest_naive_mae"] = result.backtest.naive_mae
        row["backtest_skill_vs_naive"] = result.backtest.skill_vs_naive
    else:
        for column in (
            "backtest_mae", "backtest_rmse", "backtest_mape",
            "backtest_folds", "backtest_naive_mae", "backtest_skill_vs_naive",
        ):
            row[column] = np.nan
    return row
