"""Tests for the forecasting models, engine and backtesting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.forecasting.engine import (
    STATUS_INSUFFICIENT,
    STATUS_OK,
    forecast_series,
)
from app.forecasting.models import (
    DampedTrendModel,
    HoltLinearModel,
    LinearTrendModel,
    NaiveDriftModel,
    candidate_models,
    clean_series,
)
from app.forecasting.validation import (
    rolling_origin_backtest,
    summarise_backtests,
)

ALL_MODELS = [
    NaiveDriftModel(),
    LinearTrendModel(),
    HoltLinearModel(),
    DampedTrendModel(),
]


def _series(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "reporting_month": pd.date_range("2024-10-01", periods=len(values), freq="MS"),
            "total_incomplete_pathways": values,
        }
    )


class TestModels:
    @pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.name)
    def test_output_shape(self, model):
        values = np.linspace(1000, 1500, 12)
        output = model.fit_predict(values, horizon=6)
        assert len(output.point) == 6
        assert len(output.lower) == 6
        assert len(output.upper) == 6

    @pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.name)
    def test_forecasts_never_negative(self, model):
        # A steeply falling series must not project a negative waiting list.
        values = np.array([1000.0, 800, 600, 400, 200, 100, 50, 25, 12, 6, 3, 2])
        output = model.fit_predict(values, horizon=6)
        assert all(v >= 0 for v in output.point)
        assert all(v >= 0 for v in output.lower)

    @pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.name)
    def test_interval_brackets_the_point(self, model):
        values = np.linspace(1000, 1500, 12) + np.array(
            [0, 20, -15, 30, -10, 5, 12, -22, 8, -5, 17, -9]
        )
        output = model.fit_predict(values, horizon=6)
        for lower, point, upper in zip(output.lower, output.point, output.upper, strict=False):
            assert lower <= point <= upper or lower == 0.0

    @pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.name)
    def test_interval_widens_with_horizon(self, model):
        values = np.linspace(1000, 1500, 12)
        output = model.fit_predict(values, horizon=6)
        first = output.upper[0] - output.lower[0]
        last = output.upper[5] - output.lower[5]
        assert last >= first

    def test_linear_trend_recovers_a_known_slope(self):
        values = np.array([100.0 + 10 * i for i in range(12)])
        output = LinearTrendModel().fit_predict(values, horizon=3)
        assert output.parameters["slope"] == pytest.approx(10.0, abs=1e-6)
        assert output.point[0] == pytest.approx(220.0, abs=1e-6)

    def test_naive_drift_on_flat_series(self):
        values = np.array([500.0] * 10)
        output = NaiveDriftModel().fit_predict(values, horizon=3)
        assert all(v == pytest.approx(500.0) for v in output.point)

    def test_damped_trend_is_below_undamped(self):
        """Damping should pull long horizons back towards the current level."""
        values = np.array([100.0 + 20 * i for i in range(14)])
        damped = DampedTrendModel().fit_predict(values, horizon=6)
        holt = HoltLinearModel().fit_predict(values, horizon=6)
        assert damped.point[5] < holt.point[5]

    def test_candidate_models_scale_with_history(self):
        assert len(candidate_models(6)) < len(candidate_models(12))


class TestCleanSeries:
    def test_interpolates_a_single_interior_gap(self):
        result = clean_series(pd.Series([100.0, np.nan, 300.0]))
        assert len(result) == 3
        assert result[1] == pytest.approx(200.0)

    def test_drops_leading_and_trailing_gaps(self):
        result = clean_series(pd.Series([np.nan, 100.0, 200.0, np.nan]))
        assert list(result) == [100.0, 200.0]

    def test_long_gap_is_not_bridged(self):
        result = clean_series(
            pd.Series([100.0, np.nan, np.nan, np.nan, np.nan, 600.0])
        )
        assert len(result) < 6


class TestBacktest:
    @pytest.mark.parametrize("model", ALL_MODELS, ids=lambda m: m.name)
    def test_produces_metrics(self, model):
        values = np.linspace(1000, 1600, 18)
        result = rolling_origin_backtest(values, model)
        assert result.folds > 0
        assert np.isfinite(result.mae)
        assert np.isfinite(result.rmse)
        assert result.rmse >= result.mae  # RMSE >= MAE always

    def test_short_series_returns_empty_result(self):
        result = rolling_origin_backtest(np.array([1.0, 2.0, 3.0]), NaiveDriftModel())
        assert result.folds == 0
        assert np.isnan(result.mae)

    def test_perfect_linear_series_has_near_zero_error(self):
        values = np.array([100.0 + 10 * i for i in range(18)])
        result = rolling_origin_backtest(values, LinearTrendModel())
        assert result.mae < 1e-6

    def test_skill_vs_naive_is_computed(self):
        values = np.array([100.0 + 10 * i for i in range(18)])
        result = rolling_origin_backtest(values, LinearTrendModel())
        # A perfect linear model must beat naive on a perfectly linear series.
        assert result.beats_naive

    def test_summarise_handles_empty(self):
        summary = summarise_backtests(pd.DataFrame())
        assert summary["series_forecast"] == 0
        assert summary["median_mape"] is None


class TestForecastEngine:
    def test_insufficient_history_is_reported_not_faked(self):
        result = forecast_series(_series([100.0, 110.0, 120.0]), "P", "S")
        assert result.status == STATUS_INSUFFICIENT
        assert result.horizons == {}
        assert "usable monthly observations" in result.message

    def test_successful_forecast(self):
        values = [1000.0 + 50 * i for i in range(18)]
        result = forecast_series(_series(values), "P", "S")
        assert result.status == STATUS_OK
        assert set(result.horizons) == {1, 3, 6}
        assert result.model is not None
        assert result.backtest is not None

    def test_forecast_months_advance_correctly(self):
        values = [1000.0 + 50 * i for i in range(18)]
        result = forecast_series(_series(values), "P", "S")
        # Series starts 2024-10 with 18 points -> last actual 2026-03.
        assert result.last_actual_month == "2026-03"
        assert result.forecast_months[1] == "2026-04"
        assert result.forecast_months[3] == "2026-06"
        assert result.forecast_months[6] == "2026-09"

    def test_growing_series_forecasts_growth(self):
        values = [1000.0 + 100 * i for i in range(18)]
        result = forecast_series(_series(values), "P", "S")
        assert result.forecast_change_3m_pct > 0

    def test_falling_series_forecasts_decline(self):
        values = [5000.0 - 100 * i for i in range(18)]
        result = forecast_series(_series(values), "P", "S")
        assert result.forecast_change_3m_pct < 0

    def test_confidence_label_is_assigned(self):
        values = [1000.0 + 50 * i for i in range(18)]
        result = forecast_series(_series(values), "P", "S")
        assert result.confidence in {
            "High", "Moderate", "Low", "Insufficient data"
        }

    def test_all_series_get_a_row(self, forecasts: pd.DataFrame, metrics: pd.DataFrame):
        expected = metrics.groupby(["provider_code", "specialty_code"]).ngroups
        assert len(forecasts) == expected

    def test_forecast_frame_has_required_columns(self, forecasts: pd.DataFrame):
        for column in (
            "forecast_status", "forecast_model", "forecast_confidence",
            "forecast_1m", "forecast_3m", "forecast_6m",
            "forecast_3m_lower", "forecast_3m_upper", "forecast_change_3m_pct",
            "backtest_mae", "backtest_mape", "backtest_skill_vs_naive",
        ):
            assert column in forecasts.columns

    def test_no_negative_forecasts_in_the_panel(self, forecasts: pd.DataFrame):
        for column in ("forecast_1m", "forecast_3m", "forecast_6m"):
            values = forecasts[column].dropna()
            assert (values >= 0).all()
