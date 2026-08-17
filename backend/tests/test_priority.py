"""Tests for the operational priority score."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics.narrative import build_drivers, build_service_briefing
from app.analytics.priority import (
    COMPONENT_WEIGHTS,
    COMPONENTS,
    band_for_score,
    band_metadata,
    component_metadata,
    score_snapshot,
)


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0, "LOW"), (24.9, "LOW"),
            (25, "MODERATE"), (49.9, "MODERATE"),
            (50, "HIGH"), (74.9, "HIGH"),
            (75, "CRITICAL"), (100, "CRITICAL"),
        ],
    )
    def test_band_boundaries(self, score, expected):
        assert band_for_score(score) == expected

    def test_nan_is_unscored(self):
        assert band_for_score(float("nan")) == "UNSCORED"
        assert band_for_score(None) == "UNSCORED"

    def test_band_metadata_covers_full_range(self):
        bands = band_metadata()
        assert len(bands) == 4
        assert bands[0]["min_score"] == 0
        assert bands[-1]["max_score"] == 100


class TestWeights:
    def test_weights_sum_to_100(self):
        assert sum(COMPONENT_WEIGHTS.values()) == pytest.approx(100.0)

    def test_metadata_matches_components(self):
        meta = component_metadata()
        assert len(meta) == len(COMPONENTS)
        assert {m["key"] for m in meta} == set(COMPONENT_WEIGHTS)


class TestScoring:
    def test_produces_score_and_band(self, scored: pd.DataFrame):
        assert "priority_score" in scored.columns
        assert "priority_band" in scored.columns
        assert scored.loc[scored["is_rankable"], "priority_score"].notna().all()

    def test_scores_bounded_0_100(self, scored: pd.DataFrame):
        values = scored["priority_score"].dropna()
        assert (values >= 0).all()
        assert (values <= 100).all()

    def test_components_present_and_bounded(self, scored: pd.DataFrame):
        for component in COMPONENTS:
            score_column = f"score_{component.key}"
            contribution_column = f"contribution_{component.key}"
            assert score_column in scored.columns
            assert contribution_column in scored.columns
            assert (scored[score_column].dropna() >= 0).all()
            assert (scored[score_column].dropna() <= 100).all()
            assert (
                scored[contribution_column].dropna() <= component.weight + 1e-6
            ).all()

    def test_contributions_sum_to_total(self, scored: pd.DataFrame):
        """The score must be fully decomposable - this is the core promise of
        the 'why this score?' panel."""
        columns = [f"contribution_{c.key}" for c in COMPONENTS]
        rows = scored[scored["priority_score"].notna()]
        summed = rows[columns].sum(axis=1)
        assert np.allclose(summed, rows["priority_score"], atol=0.15)

    def test_band_matches_score(self, scored: pd.DataFrame):
        for _, row in scored.iterrows():
            if pd.isna(row["priority_score"]):
                assert row["priority_band"] == "UNSCORED"
            else:
                assert row["priority_band"] == band_for_score(row["priority_score"])

    def test_ranking_is_monotone_in_score(self, scored: pd.DataFrame):
        rankable = scored[scored["is_rankable"]].sort_values("priority_rank")
        scores = rankable["priority_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_small_lists_marked_unrankable_and_unscored(
        self, metrics: pd.DataFrame
    ):
        """A service below the threshold must not receive a band.

        Every component would fall back to the neutral 50, giving a total of
        exactly 50 - which lands in HIGH. Presenting that as a finding would be
        an artefact of the defaults, not a statement about the service.
        """
        from app.analytics.metrics import latest_snapshot

        snapshot = latest_snapshot(metrics).copy()
        snapshot.loc[snapshot.index[0], "total_incomplete_pathways"] = 10.0
        result = score_snapshot(snapshot)

        assert not bool(result["is_rankable"].iloc[0])
        assert pd.isna(result["priority_score"].iloc[0])
        assert result["priority_band"].iloc[0] == "UNSCORED"

    def test_unscored_services_never_land_in_a_pressure_band(
        self, scored: pd.DataFrame
    ):
        unscored = scored[scored["priority_score"].isna()]
        assert (unscored["priority_band"] == "UNSCORED").all()

    def test_rankable_services_are_all_scored(self, scored: pd.DataFrame):
        rankable = scored[scored["is_rankable"]]
        assert rankable["priority_score"].notna().all()
        assert (rankable["priority_band"] != "UNSCORED").all()

    def test_empty_snapshot_returns_empty(self):
        assert score_snapshot(pd.DataFrame()).empty

    def test_missing_forecast_scores_neutrally(self, metrics: pd.DataFrame):
        from app.analytics.metrics import latest_snapshot

        snapshot = latest_snapshot(metrics).copy()
        # No forecast columns at all.
        result = score_snapshot(snapshot)
        assert (result["score_forecast_risk"] == 50.0).all()


class TestDrivers:
    def test_drivers_are_generated(self, scored: pd.DataFrame):
        drivers = build_drivers(scored.iloc[0].to_dict())
        assert len(drivers) > 0
        assert all(isinstance(d, str) and d for d in drivers)

    def test_drivers_ordered_by_contribution(self, scored: pd.DataFrame):
        row = scored.sort_values("priority_score", ascending=False).iloc[0].to_dict()
        drivers = build_drivers(row)
        labels = [d.split(":")[0] for d in drivers]
        contributions = [
            row[f"contribution_{c.key}"]
            for c in COMPONENTS
            if c.label in labels
        ]
        # The first listed driver must be the largest contributor present.
        assert contributions[0] == max(contributions) or len(contributions) == 1


class TestBriefing:
    def test_briefing_has_sections(self, scored: pd.DataFrame):
        row = scored.iloc[0].to_dict()
        briefing = build_service_briefing(row, "Test Trust", "Test Specialty")
        assert briefing.headline
        assert len(briefing.sections) > 0
        assert len(briefing.recommended_actions) > 0
        assert len(briefing.caveats) > 0

    def test_briefing_omits_sections_without_data(self):
        """A missing metric must produce no sentence, never a fabricated one."""
        sparse = {
            "priority_band": "LOW",
            "priority_score": 10.0,
            "total_incomplete_pathways": None,
            "forecast_status": "insufficient_history",
            "forecast_message": "Not enough history.",
        }
        briefing = build_service_briefing(sparse, "Trust", "Specialty")
        titles = [s["title"] for s in briefing.sections]
        assert "Current position" not in titles
        assert "Trend" not in titles

    def test_briefing_reports_missing_forecast_honestly(self):
        sparse = {
            "priority_band": "MODERATE",
            "priority_score": 30.0,
            "total_incomplete_pathways": 500.0,
            "forecast_status": "insufficient_history",
            "forecast_message": "Only 3 usable monthly observations.",
        }
        briefing = build_service_briefing(sparse, "Trust", "Specialty")
        outlook = next(s for s in briefing.sections if s["title"] == "Outlook")
        assert "3 usable monthly observations" in outlook["body"]

    def test_no_fabricated_performance_claims(self, scored: pd.DataFrame):
        """Guard against language implying an achieved outcome."""
        briefing = build_service_briefing(
            scored.iloc[0].to_dict(), "Trust", "Specialty"
        )
        text = briefing.as_text().lower()
        for phrase in ("reduced waiting", "saved", "improved patient outcomes",
                       "deployed across", "used by nhs england"):
            assert phrase not in text
