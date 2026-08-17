"""Tests for derived metrics and the numeric helpers they rely on."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics.metrics import add_trend_metrics
from app.utils.mathx import (
    clipped_robust_scale,
    linear_trend_slope,
    pct_change_over,
    percentile_rank,
    robust_zscore,
    safe_divide,
)


class TestSafeDivide:
    def test_divides_normally(self):
        result = safe_divide(pd.Series([10.0, 20.0]), pd.Series([2.0, 4.0]))
        assert list(result) == [5.0, 5.0]

    def test_zero_denominator_yields_nan_not_inf(self):
        # A specialty appearing for the first time has a zero baseline. An inf
        # here would poison every downstream percentile.
        result = safe_divide(pd.Series([10.0]), pd.Series([0.0]))
        assert result.isna().all()

    def test_missing_denominator_yields_nan(self):
        result = safe_divide(pd.Series([10.0]), pd.Series([np.nan]))
        assert result.isna().all()

    def test_scalar_division(self):
        assert safe_divide(10.0, 4.0) == pytest.approx(2.5)
        assert np.isnan(safe_divide(10.0, 0.0))

    def test_custom_fill(self):
        result = safe_divide(pd.Series([1.0]), pd.Series([0.0]), fill=0.0)
        assert list(result) == [0.0]


class TestPercentileRank:
    def test_scales_to_0_100(self):
        result = percentile_rank(pd.Series([1.0, 2.0, 3.0, 4.0]))
        assert result.min() >= 0
        assert result.max() <= 100
        assert result.iloc[-1] == pytest.approx(100.0)

    def test_preserves_order(self):
        values = pd.Series([5.0, 1.0, 3.0])
        ranked = percentile_rank(values)
        assert ranked.iloc[0] > ranked.iloc[2] > ranked.iloc[1]

    def test_nan_stays_nan(self):
        result = percentile_rank(pd.Series([1.0, np.nan, 3.0]))
        assert bool(result.isna().iloc[1])

    def test_all_nan_returns_all_nan(self):
        result = percentile_rank(pd.Series([np.nan, np.nan]))
        assert result.isna().all()

    def test_single_value_is_neutral(self):
        result = percentile_rank(pd.Series([np.nan, 7.0]))
        assert result.iloc[1] == 50.0


class TestClippedRobustScale:
    def test_bounded_0_100(self):
        values = pd.Series([0.0, 1.0, 2.0, 3.0, 100.0])
        result = clipped_robust_scale(values)
        assert result.min() >= 0
        assert result.max() <= 100

    def test_outlier_does_not_compress_the_rest(self):
        # This is the reason min-max is avoided for the score components.
        values = pd.Series([*np.linspace(0, 10, 20), 100000.0])
        result = clipped_robust_scale(values)
        spread = result.iloc[:20].max() - result.iloc[:20].min()
        assert spread > 50


class TestLinearTrendSlope:
    def test_positive_slope(self):
        assert linear_trend_slope(pd.Series([1.0, 2.0, 3.0, 4.0])) == pytest.approx(1.0)

    def test_negative_slope(self):
        assert linear_trend_slope(pd.Series([4.0, 3.0, 2.0])) == pytest.approx(-1.0)

    def test_flat_series_is_zero(self):
        assert linear_trend_slope(pd.Series([5.0, 5.0, 5.0])) == pytest.approx(0.0)

    def test_insufficient_data_returns_nan(self):
        assert np.isnan(linear_trend_slope(pd.Series([1.0])))
        assert np.isnan(linear_trend_slope(pd.Series([], dtype=float)))


class TestPctChangeOver:
    def test_three_period_change(self):
        series = pd.Series([100.0, 110.0, 120.0, 130.0])
        result = pct_change_over(series, 3)
        assert result.iloc[3] == pytest.approx(30.0)

    def test_zero_baseline_is_nan(self):
        result = pct_change_over(pd.Series([0.0, 50.0]), 1)
        assert bool(result.isna().iloc[1])


class TestRobustZscore:
    def test_flags_an_outlier(self):
        values = pd.Series([10.0, 11.0, 10.5, 10.2, 300.0])
        result = robust_zscore(values)
        assert abs(result.iloc[-1]) > 3.5

    def test_flat_series_returns_nan(self):
        # Zero MAD: a perfectly flat series has no meaningful outliers.
        result = robust_zscore(pd.Series([5.0] * 10))
        assert result.isna().all()


class TestTrendMetrics:
    def test_adds_expected_columns(self, metrics: pd.DataFrame):
        for column in (
            "backlog_change_1m", "backlog_growth_3m_pct", "backlog_growth_6m_pct",
            "waiting_list_rolling_3m", "trend_slope_6m", "months_backlog_rising",
            "rolling_activity_3m", "implied_additions", "activity_gap_pct",
            "months_to_clear_at_current_activity",
        ):
            assert column in metrics.columns

    def test_first_month_has_no_prior_change(self, metrics: pd.DataFrame):
        # nth(0), not first(): groupby.first() skips nulls and would return a
        # later month's value, which is exactly what this test must not do.
        first_rows = (
            metrics.sort_values("reporting_month")
            .groupby(["provider_code", "specialty_code"], as_index=False)
            .nth(0)
        )
        assert first_rows["backlog_change_1m"].isna().all()
        assert first_rows["backlog_growth_3m_pct"].isna().all()

    def test_growth_matches_manual_calculation(self, metrics: pd.DataFrame):
        series = metrics[
            (metrics["provider_code"] == "P00")
            & (metrics["specialty_code"] == "C_100")
        ].sort_values("reporting_month").reset_index(drop=True)

        current = series["total_incomplete_pathways"].iloc[5]
        prior = series["total_incomplete_pathways"].iloc[2]
        expected = (current - prior) / prior * 100.0
        assert series["backlog_growth_3m_pct"].iloc[5] == pytest.approx(expected)

    def test_percentages_within_range(self, metrics: pd.DataFrame):
        pct = metrics["pct_within_18_weeks"].dropna()
        assert (pct >= 0).all()
        assert (pct <= 100).all()

    def test_over_18_never_negative(self, metrics: pd.DataFrame):
        assert (metrics["over_18_weeks"].dropna() >= 0).all()

    def test_components_do_not_exceed_total(self, metrics: pd.DataFrame):
        assert (
            metrics["within_18_weeks"] <= metrics["total_incomplete_pathways"]
        ).all()

    def test_implied_additions_is_an_identity(self, metrics: pd.DataFrame):
        # backlog_change = implied_additions - completed_pathways
        subset = metrics.dropna(
            subset=["implied_additions", "completed_pathways", "backlog_change_1m"]
        )
        reconstructed = subset["implied_additions"] - subset["completed_pathways"]
        assert np.allclose(reconstructed, subset["backlog_change_1m"])

    def test_consecutive_rising_counts_reset(self):
        frame = pd.DataFrame(
            {
                "provider_code": ["A"] * 6,
                "specialty_code": ["S"] * 6,
                "reporting_month": pd.date_range("2025-01-01", periods=6, freq="MS"),
                "total_incomplete_pathways": [100.0, 110.0, 120.0, 90.0, 95.0, 100.0],
                "within_18_weeks": [50.0] * 6,
                "over_18_weeks": [50.0] * 6,
                "pct_within_18_weeks": [50.0] * 6,
                "completed_pathways": [10.0] * 6,
            }
        )
        result = add_trend_metrics(frame)
        runs = result["months_backlog_rising"].tolist()
        assert runs[2] == 2.0   # two consecutive rises
        assert runs[3] == 0.0   # reset by the fall
        assert runs[5] == 2.0   # two rises again

    def test_empty_frame_is_handled(self):
        assert add_trend_metrics(pd.DataFrame()).empty
