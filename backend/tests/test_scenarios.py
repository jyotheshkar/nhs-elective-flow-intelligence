"""Tests for the illustrative capacity scenario engine.

The invariants here are what make the scenario defensible: no uplift means no
change, more activity never increases the modelled backlog, and the result can
never go negative.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.scenarios.engine import (
    DEFAULT_UPLIFTS,
    STATUS_OK,
    UNAVAILABLE_NO_ACTIVITY,
    UNAVAILABLE_NO_FORECAST,
    run_scenario,
    run_scenario_set,
    scenario_assumptions,
)


@pytest.fixture
def history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "provider_code": ["P01"] * 6,
            "specialty_code": ["C_110"] * 6,
            "reporting_month": pd.date_range("2025-10-01", periods=6, freq="MS"),
            "total_incomplete_pathways": [
                5000.0, 5100.0, 5200.0, 5300.0, 5400.0, 5500.0
            ],
            "completed_pathways": [500.0, 500.0, 500.0, 600.0, 600.0, 600.0],
        }
    )


@pytest.fixture
def forecast_row() -> dict:
    return {
        "forecast_status": "ok",
        "forecast_last_actual": 5500.0,
        "forecast_1m": 5600.0,
        "forecast_3m": 5800.0,
        "forecast_6m": 6100.0,
        "forecast_1m_month": "2026-04",
        "forecast_3m_month": "2026-06",
        "forecast_6m_month": "2026-09",
    }


class TestScenarioInvariants:
    def test_zero_uplift_equals_baseline(self, history, forecast_row):
        """The defining invariant: 0% must reproduce the baseline exactly."""
        result = run_scenario(history, forecast_row, uplift_pct=0.0)
        assert result.status == STATUS_OK
        for point in result.points:
            assert point.scenario_backlog == point.baseline_backlog
            assert point.difference_from_baseline == 0.0

    def test_more_activity_never_increases_backlog(self, history, forecast_row):
        results = run_scenario_set(history, forecast_row, uplifts=DEFAULT_UPLIFTS)
        by_horizon: dict[int, list[float]] = {}
        for result in results:
            for point in result.points:
                by_horizon.setdefault(point.horizon_months, []).append(
                    point.scenario_backlog
                )
        for horizon, values in by_horizon.items():
            assert values == sorted(values, reverse=True), (
                f"horizon {horizon} is not monotonically decreasing in uplift"
            )

    def test_backlog_never_negative(self, history, forecast_row):
        # An extreme uplift must floor at zero, not go negative.
        result = run_scenario(history, forecast_row, uplift_pct=100.0)
        for point in result.points:
            assert point.scenario_backlog >= 0.0

    def test_uplift_is_clamped(self, history, forecast_row):
        assert run_scenario(history, forecast_row, uplift_pct=-50.0).uplift_pct == 0.0
        assert run_scenario(history, forecast_row, uplift_pct=500.0).uplift_pct == 100.0

    def test_effect_accumulates_with_horizon(self, history, forecast_row):
        result = run_scenario(history, forecast_row, uplift_pct=10.0)
        differences = {p.horizon_months: abs(p.difference_from_baseline)
                       for p in result.points}
        assert differences[6] > differences[3] > differences[1]


class TestScenarioArithmetic:
    def test_baseline_activity_is_a_three_month_mean(self, history, forecast_row):
        result = run_scenario(history, forecast_row, uplift_pct=10.0)
        # Last three months of completed activity: 600, 600, 600.
        assert result.baseline_monthly_activity == pytest.approx(600.0)
        assert result.additional_monthly_activity == pytest.approx(60.0)

    def test_scenario_subtracts_cumulative_activity(self, history, forecast_row):
        result = run_scenario(history, forecast_row, uplift_pct=10.0)
        three_month = next(p for p in result.points if p.horizon_months == 3)
        # 5800 baseline - (3 months x 60 extra) = 5620
        assert three_month.scenario_backlog == pytest.approx(5620.0)
        assert three_month.additional_activity_cumulative == pytest.approx(180.0)

    def test_uplift_to_stabilise(self, history, forecast_row):
        result = run_scenario(history, forecast_row, uplift_pct=0.0)
        # growth = 5800 - 5500 = 300 over 3 months; 300 / (3 * 600) = 16.7%
        assert result.uplift_required_to_stabilise_pct == pytest.approx(16.7, abs=0.1)
        assert result.stabilisation_feasible

    def test_no_uplift_needed_when_list_is_falling(self, history):
        improving = {
            "forecast_status": "ok",
            "forecast_last_actual": 5500.0,
            "forecast_1m": 5400.0,
            "forecast_3m": 5200.0,
            "forecast_6m": 5000.0,
            "forecast_1m_month": "2026-04",
            "forecast_3m_month": "2026-06",
            "forecast_6m_month": "2026-09",
        }
        result = run_scenario(history, improving, uplift_pct=0.0)
        assert result.uplift_required_to_stabilise_pct == 0.0
        assert result.stabilisation_feasible


class TestScenarioUnavailable:
    def test_without_a_forecast(self, history):
        result = run_scenario(
            history,
            {"forecast_status": "insufficient_history",
             "forecast_message": "Not enough history."},
            uplift_pct=10.0,
        )
        assert result.status == UNAVAILABLE_NO_FORECAST
        assert result.points == []
        assert "cannot be projected" in result.message

    def test_without_activity_data(self, history, forecast_row):
        no_activity = history.copy()
        no_activity["completed_pathways"] = None
        result = run_scenario(no_activity, forecast_row, uplift_pct=10.0)
        assert result.status == UNAVAILABLE_NO_ACTIVITY
        assert "cannot be modelled" in result.message

    def test_zero_activity_is_not_divided_by(self, history, forecast_row):
        zero = history.copy()
        zero["completed_pathways"] = 0.0
        result = run_scenario(zero, forecast_row, uplift_pct=10.0)
        assert result.status == UNAVAILABLE_NO_ACTIVITY


class TestScenarioLabelling:
    def test_assumptions_are_always_attached(self, history, forecast_row):
        result = run_scenario(history, forecast_row, uplift_pct=10.0)
        assert len(result.assumptions) >= 5

    def test_assumptions_disclaim_causality(self):
        text = " ".join(scenario_assumptions()).lower()
        assert "modelled estimates" in text
        assert "not predicted outcomes" in text
        assert "assumed unchanged" in text

    def test_assumptions_present_even_when_unavailable(self, history):
        result = run_scenario(
            history, {"forecast_status": "insufficient_history"}, uplift_pct=10.0
        )
        assert len(result.assumptions) >= 5
