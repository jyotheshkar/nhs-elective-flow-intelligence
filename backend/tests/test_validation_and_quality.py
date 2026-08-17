"""Tests for schema validation, cleaning and the data quality engine."""

from __future__ import annotations

import pandas as pd
import pytest

from app.quality.checks import (
    check_anomalies,
    check_completeness,
    check_consistency,
    check_freshness,
)
from app.quality.score import WEIGHTS, build_quality_report, provider_quality_scores
from app.transformation.cleaning import (
    short_provider_name,
    short_specialty_name,
    title_case_provider,
)
from app.transformation.schema import build_column_map, normalise_caption
from app.transformation.validation import validate_canonical_fact, validate_raw_frame


class TestCaptionNormalisation:
    def test_collapses_whitespace_and_case(self):
        assert normalise_caption("  Total   Number Of  Incomplete Pathways ") == (
            "total number of incomplete pathways"
        )

    def test_handles_non_breaking_space(self):
        assert normalise_caption("Provider\u00a0Code") == "provider code"

    def test_none_is_empty(self):
        assert normalise_caption(None) == ""


class TestColumnMapping:
    def test_maps_published_captions(self):
        from app.transformation.schema import INCOMPLETE_SPEC

        captions = [
            "Region Code", "Provider Code", "Provider Name",
            "Treatment Function Code", "Treatment Function",
            ">0-1", ">1-2", "104 plus",
            "Total number of incomplete pathways", "Total within 18 weeks",
            "% within 18 weeks", "Total 52 plus weeks",
        ]
        mapping = build_column_map(captions, INCOMPLETE_SPEC)
        assert mapping[1] == "provider_code"
        assert mapping[3] == "specialty_code"
        assert mapping[7] == "over_104_weeks"
        assert mapping[8] == "total_incomplete_pathways"
        # Weekly bands other than '104 plus' are not part of the model.
        assert 5 not in mapping

    def test_duplicate_captions_map_once(self):
        from app.transformation.schema import INCOMPLETE_SPEC

        captions = ["Provider Code", "Provider Code"]
        mapping = build_column_map(captions, INCOMPLETE_SPEC)
        assert list(mapping.values()).count("provider_code") == 1


class TestNameCleaning:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ALDER HEY CHILDREN'S NHS FOUNDATION TRUST",
             "Alder Hey Children's NHS Foundation Trust"),
            ("ST GEORGE'S UNIVERSITY HOSPITALS NHS FOUNDATION TRUST",
             "St George's University Hospitals NHS Foundation Trust"),
            ("UNIVERSITY HOSPITALS COVENTRY AND WARWICKSHIRE NHS TRUST",
             "University Hospitals Coventry and Warwickshire NHS Trust"),
            ("THE QUEEN ELIZABETH HOSPITAL, KING'S LYNN,",
             "The Queen Elizabeth Hospital, King's Lynn"),
        ],
    )
    def test_title_casing(self, raw, expected):
        assert title_case_provider(raw) == expected

    def test_none_passes_through(self):
        assert title_case_provider(None) is None

    def test_short_name_drops_trust_suffix(self):
        assert short_provider_name("BARTS HEALTH NHS TRUST") == "Barts Health"
        assert short_provider_name("AIREDALE NHS FOUNDATION TRUST") == "Airedale"

    def test_short_specialty_drops_service_suffix(self):
        assert short_specialty_name("Trauma and Orthopaedic Service") == (
            "Trauma and Orthopaedic"
        )
        assert short_specialty_name("Other - Other Services") == (
            "Other - Other Services"
        )


class TestRawValidation:
    def test_valid_frame_passes(self, raw_panel: pd.DataFrame):
        report = validate_raw_frame(
            raw_panel,
            "test",
            ("provider_code", "specialty_code", "total_incomplete_pathways"),
        )
        assert report.passed
        assert report.errors == []

    def test_missing_column_is_an_error(self):
        frame = pd.DataFrame({"provider_code": ["A"]})
        report = validate_raw_frame(frame, "test", ("provider_code", "missing_col"))
        assert not report.passed
        assert any("missing_col" in issue.message for issue in report.errors)

    def test_empty_frame_fails(self):
        report = validate_raw_frame(pd.DataFrame(), "test", ("provider_code",))
        assert not report.passed

    def test_negative_values_warn_but_do_not_fail(self):
        frame = pd.DataFrame(
            {
                "provider_code": ["A"],
                "specialty_code": ["S"],
                "total_incomplete_pathways": [-10.0],
                "within_18_weeks": [5.0],
            }
        )
        report = validate_raw_frame(
            frame, "test", ("provider_code", "total_incomplete_pathways")
        )
        assert report.passed  # row-level issues are non-fatal
        assert any("negative" in i.message.lower() for i in report.warnings)

    def test_component_exceeding_total_warns(self):
        frame = pd.DataFrame(
            {
                "provider_code": ["A"],
                "specialty_code": ["S"],
                "total_incomplete_pathways": [100.0],
                "within_18_weeks": [150.0],
            }
        )
        report = validate_raw_frame(frame, "test", ("provider_code",))
        assert any("exceeds" in i.message for i in report.warnings)

    def test_band_nesting_warns(self):
        frame = pd.DataFrame(
            {
                "provider_code": ["A"],
                "specialty_code": ["S"],
                "over_52_weeks": [10.0],
                "over_65_weeks": [50.0],  # cannot exceed 52+
            }
        )
        report = validate_raw_frame(frame, "test", ("provider_code",))
        assert any("over_65_weeks" in i.check for i in report.warnings)


class TestFactValidation:
    def test_canonical_fact_passes(self, fact: pd.DataFrame):
        assert validate_canonical_fact(fact).passed

    def test_duplicate_grain_fails(self, fact: pd.DataFrame):
        duplicated = pd.concat([fact, fact.head(1)], ignore_index=True)
        report = validate_canonical_fact(duplicated)
        assert not report.passed
        assert any("duplicate" in i.message.lower() for i in report.errors)


class TestQualityChecks:
    def test_completeness_metrics(self, fact, dim_provider, dim_specialty):
        _issues, metrics = check_completeness(fact, dim_provider, dim_specialty)
        assert 0 <= metrics["value_completeness_pct"] <= 100
        assert 0 <= metrics["panel_completeness_pct"] <= 100
        assert metrics["reporting_months"] == 18

    def test_missing_month_is_detected(self, fact, dim_provider, dim_specialty):
        gapped = fact[
            ~(
                (fact["provider_code"] == "P00")
                & (fact["specialty_code"] == "C_100")
                & (fact["month_key"] == "2025-03")
            )
        ]
        issues, metrics = check_completeness(gapped, dim_provider, dim_specialty)
        assert metrics["missing_month_gaps"] >= 1
        assert any(i.issue_type == "Missing reporting months" for i in issues)

    def test_consistency_on_clean_data(self, fact, dim_provider, dim_specialty):
        _issues, metrics = check_consistency(fact, dim_provider, dim_specialty)
        assert metrics["consistency_pct"] > 99

    def test_negative_value_is_flagged(self, fact, dim_provider, dim_specialty):
        corrupted = fact.copy()
        corrupted.loc[corrupted.index[0], "total_incomplete_pathways"] = -50.0
        issues, _metrics = check_consistency(corrupted, dim_provider, dim_specialty)
        assert any(i.issue_type == "Negative count" for i in issues)
        assert any(i.severity == "High" for i in issues)

    def test_duplicate_row_is_flagged(self, fact, dim_provider, dim_specialty):
        duplicated = pd.concat([fact, fact.head(1)], ignore_index=True)
        issues, _metrics = check_consistency(duplicated, dim_provider, dim_specialty)
        assert any(i.issue_type == "Duplicate record" for i in issues)

    def test_freshness(self, fact: pd.DataFrame):
        _issues, metrics = check_freshness(fact)
        assert "freshness_pct" in metrics
        assert 0 <= metrics["freshness_pct"] <= 100
        assert metrics["latest_month"] == "2026-03"

    def test_freshness_on_empty(self):
        issues, metrics = check_freshness(pd.DataFrame())
        assert issues == []
        assert metrics["freshness_pct"] == 0.0

    def test_anomaly_detection_flags_a_spike(
        self, fact, dim_provider, dim_specialty
    ):
        spiked = fact.copy()
        mask = (
            (spiked["provider_code"] == "P00")
            & (spiked["specialty_code"] == "C_100")
            & (spiked["month_key"] == "2025-06")
        )
        spiked.loc[mask, "total_incomplete_pathways"] *= 4
        issues, metrics = check_anomalies(spiked, dim_provider, dim_specialty)
        assert metrics["anomaly_count"] > 0
        assert any(i.issue_type == "Unusual month-on-month change" for i in issues)

    def test_anomaly_language_is_not_accusatory(
        self, fact, dim_provider, dim_specialty
    ):
        """Flagged movements must be described as requiring review, not as
        errors in the published data."""
        spiked = fact.copy()
        mask = spiked.index == spiked.index[20]
        spiked.loc[mask, "total_incomplete_pathways"] *= 5
        issues, _ = check_anomalies(spiked, dim_provider, dim_specialty)
        if issues:
            assert any("May reflect" in i.description for i in issues)


class TestQualityScore:
    def test_weights_sum_to_100(self):
        assert sum(WEIGHTS.values()) == pytest.approx(100.0)

    def test_report_structure(self, fact, dim_provider, dim_specialty):
        report = build_quality_report(fact, dim_provider, dim_specialty)
        assert 0 <= report.overall_score <= 100
        assert set(report.dimension_scores) == set(WEIGHTS)
        for score in report.dimension_scores.values():
            assert 0 <= score <= 100

    def test_contributions_sum_to_overall(self, fact, dim_provider, dim_specialty):
        report = build_quality_report(fact, dim_provider, dim_specialty)
        assert sum(report.dimension_contributions.values()) == pytest.approx(
            report.overall_score, abs=0.15
        )

    def test_clean_data_scores_well(self, fact, dim_provider, dim_specialty):
        report = build_quality_report(fact, dim_provider, dim_specialty)
        assert report.overall_score > 60

    def test_issue_frame_columns(self, fact, dim_provider, dim_specialty):
        report = build_quality_report(fact, dim_provider, dim_specialty)
        frame = report.issue_frame()
        for column in ("issue_type", "severity", "description"):
            assert column in frame.columns

    def test_provider_scores(self, fact, dim_provider, dim_specialty):
        report = build_quality_report(fact, dim_provider, dim_specialty)
        scores = provider_quality_scores(report.issue_frame(), fact)
        assert "provider_quality_score" in scores.columns
        assert (scores["provider_quality_score"] <= 100).all()
        assert (scores["provider_quality_score"] >= 0).all()
