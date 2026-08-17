"""Rolling-origin backtesting for the forecast models.

Model selection uses out-of-sample error only. Every model is also scored
against a no-change naive benchmark, so the product can state plainly whether
the chosen model actually adds anything over "assume next month looks like this
month".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.utils.logging import get_logger

logger = get_logger(__name__)

# Minimum observations retained in the first training fold. Below this the fits
# are meaningless, so no backtest is attempted.
MIN_TRAIN_SIZE = 5


@dataclass
class BacktestResult:
    """Out-of-sample accuracy of one model on one series."""

    model: str
    folds: int
    mae: float
    rmse: float
    mape: float
    naive_mae: float
    skill_vs_naive: float   # 1 - (model MAE / naive MAE); >0 means it beats naive

    @property
    def beats_naive(self) -> bool:
        return np.isfinite(self.skill_vs_naive) and self.skill_vs_naive > 0


def _empty(model_name: str) -> BacktestResult:
    return BacktestResult(
        model=model_name,
        folds=0,
        mae=float("nan"),
        rmse=float("nan"),
        mape=float("nan"),
        naive_mae=float("nan"),
        skill_vs_naive=float("nan"),
    )


def rolling_origin_backtest(
    values: np.ndarray,
    model,
    horizon: int = 1,
    max_folds: int = 6,
) -> BacktestResult:
    """Expanding-window backtest.

    Trains on ``values[:k]`` and predicts ``values[k + horizon - 1]`` for
    successive origins, so every evaluation point is genuinely out of sample.
    With 18 monthly observations this yields up to 6 folds.
    """
    n = len(values)
    if n < MIN_TRAIN_SIZE + horizon:
        return _empty(getattr(model, "name", "unknown"))

    first_origin = max(MIN_TRAIN_SIZE, n - horizon - max_folds + 1)
    origins = range(first_origin, n - horizon + 1)

    errors: list[float] = []
    naive_errors: list[float] = []
    percentage_errors: list[float] = []

    for origin in origins:
        train = values[:origin]
        actual = float(values[origin + horizon - 1])
        try:
            output = model.fit_predict(train, horizon)
            predicted = float(output.point[horizon - 1])
        except (ValueError, np.linalg.LinAlgError, IndexError):
            continue
        if not np.isfinite(predicted):
            continue

        errors.append(abs(predicted - actual))
        # Naive benchmark: last observed value carried forward.
        naive_errors.append(abs(float(train[-1]) - actual))
        # MAPE is only meaningful away from zero; skip near-zero actuals rather
        # than letting them dominate the average.
        if abs(actual) > 1e-6:
            percentage_errors.append(abs(predicted - actual) / abs(actual) * 100.0)

    if not errors:
        return _empty(getattr(model, "name", "unknown"))

    error_array = np.asarray(errors, dtype="float64")
    mae = float(error_array.mean())
    rmse = float(np.sqrt((error_array**2).mean()))
    mape = (
        float(np.mean(percentage_errors)) if percentage_errors else float("nan")
    )
    naive_mae = float(np.mean(naive_errors)) if naive_errors else float("nan")
    skill = (
        1.0 - (mae / naive_mae)
        if np.isfinite(naive_mae) and naive_mae > 0
        else float("nan")
    )

    return BacktestResult(
        model=getattr(model, "name", "unknown"),
        folds=len(errors),
        mae=mae,
        rmse=rmse,
        mape=mape,
        naive_mae=naive_mae,
        skill_vs_naive=float(skill),
    )


def summarise_backtests(frame) -> dict:
    """Portfolio-level accuracy summary for the methodology page.

    Reports the median rather than the mean: forecast errors across ~3,000
    series are heavily right-skewed and a mean would be dominated by a handful
    of volatile small specialties.
    """
    import pandas as pd

    if frame is None or len(frame) == 0 or "backtest_mape" not in frame.columns:
        return {
            "series_forecast": 0,
            "series_insufficient_history": 0,
            "median_mape": None,
            "median_mae": None,
            "share_beating_naive": None,
            "confidence_distribution": {},
            "model_distribution": {},
        }

    ok = frame[frame["forecast_status"] == "ok"]
    mape = pd.to_numeric(ok.get("backtest_mape"), errors="coerce").dropna()
    mae = pd.to_numeric(ok.get("backtest_mae"), errors="coerce").dropna()
    skill = pd.to_numeric(ok.get("backtest_skill_vs_naive"), errors="coerce").dropna()

    return {
        "series_forecast": int(len(ok)),
        "series_insufficient_history": int(len(frame) - len(ok)),
        "median_mape": round(float(mape.median()), 2) if not mape.empty else None,
        "median_mae": round(float(mae.median()), 1) if not mae.empty else None,
        "share_beating_naive": (
            round(float((skill > 0).mean()) * 100.0, 1) if not skill.empty else None
        ),
        "confidence_distribution": (
            ok["forecast_confidence"].value_counts().to_dict()
            if "forecast_confidence" in ok.columns
            else {}
        ),
        "model_distribution": (
            ok["forecast_model"].value_counts().to_dict()
            if "forecast_model" in ok.columns
            else {}
        ),
    }
