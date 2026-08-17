"""Composite data quality score.

    Data Quality Score (0-100) =
        40%  Completeness   (value completeness and panel completeness)
      + 25%  Consistency    (share of integrity checks passed)
      + 20%  Freshness      (age of the latest reporting period)
      + 15%  Anomaly burden (inverse of the flagged-anomaly rate)

The weights are a stated judgement, not a standard. They are published on the
methodology page so a reviewer can disagree with them explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd

from app.quality.checks import (
    QualityIssue,
    check_anomalies,
    check_completeness,
    check_consistency,
    check_freshness,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

WEIGHTS = {
    "completeness": 40.0,
    "consistency": 25.0,
    "freshness": 20.0,
    "anomaly_burden": 15.0,
}


@dataclass
class QualityReport:
    """Full data quality assessment of the loaded warehouse."""

    overall_score: float
    dimension_scores: dict[str, float]
    dimension_contributions: dict[str, float]
    metrics: dict
    issues: list[QualityIssue] = field(default_factory=list)
    generated_at: str = ""

    def issue_frame(self) -> pd.DataFrame:
        if not self.issues:
            return pd.DataFrame(
                columns=[
                    "provider_code", "provider_name", "specialty_code",
                    "specialty_name", "month", "issue_type", "severity",
                    "description", "observed_value", "expected_value",
                ]
            )
        return pd.DataFrame([i.to_dict() for i in self.issues])


def build_quality_report(
    fact: pd.DataFrame,
    dim_provider: pd.DataFrame,
    dim_specialty: pd.DataFrame,
) -> QualityReport:
    """Run every check and combine the results into a single score."""
    completeness_issues, completeness_metrics = check_completeness(
        fact, dim_provider, dim_specialty
    )
    consistency_issues, consistency_metrics = check_consistency(
        fact, dim_provider, dim_specialty
    )
    freshness_issues, freshness_metrics = check_freshness(fact)
    anomaly_issues, anomaly_metrics = check_anomalies(
        fact, dim_provider, dim_specialty
    )

    # Completeness blends the two views: are the cells populated, and is the
    # panel rectangular?
    completeness_score = (
        completeness_metrics["value_completeness_pct"] * 0.6
        + completeness_metrics["panel_completeness_pct"] * 0.4
    )

    dimension_scores = {
        "completeness": round(completeness_score, 2),
        "consistency": consistency_metrics["consistency_pct"],
        "freshness": freshness_metrics["freshness_pct"],
        "anomaly_burden": anomaly_metrics["anomaly_burden_score"],
    }
    contributions = {
        key: round(score * WEIGHTS[key] / 100.0, 2)
        for key, score in dimension_scores.items()
    }
    overall = round(sum(contributions.values()), 1)

    issues = (
        consistency_issues + freshness_issues + anomaly_issues + completeness_issues
    )
    severity_order = {"High": 0, "Medium": 1, "Low": 2}
    issues.sort(key=lambda i: (severity_order.get(i.severity, 3), i.issue_type))

    report = QualityReport(
        overall_score=overall,
        dimension_scores=dimension_scores,
        dimension_contributions=contributions,
        metrics={
            **completeness_metrics,
            **consistency_metrics,
            **freshness_metrics,
            **anomaly_metrics,
            "weights": WEIGHTS,
            "total_issues": len(issues),
            "high_severity_issues": sum(1 for i in issues if i.severity == "High"),
        },
        issues=issues,
        generated_at=datetime.now(UTC).isoformat(),
    )
    logger.info(
        "Data quality score %.1f/100 (%d issues, %d high severity)",
        overall, len(issues), report.metrics["high_severity_issues"],
    )
    return report


def provider_quality_scores(
    issues_frame: pd.DataFrame, fact: pd.DataFrame
) -> pd.DataFrame:
    """Per-provider quality view: issue counts weighted by severity.

    Expressed as an indicative 0-100 score so it can sit next to the global
    score, with the raw counts retained so the number is auditable.
    """
    providers = fact[["provider_code"]].drop_duplicates()
    if issues_frame.empty:
        providers["quality_issues"] = 0
        providers["high_severity_issues"] = 0
        providers["provider_quality_score"] = 100.0
        return providers

    weights = {"High": 3.0, "Medium": 1.5, "Low": 0.5}
    scoped = issues_frame[issues_frame["provider_code"].notna()].copy()
    scoped["_weight"] = scoped["severity"].map(weights).fillna(0.5)

    grouped = scoped.groupby("provider_code").agg(
        quality_issues=("issue_type", "size"),
        high_severity_issues=("severity", lambda s: int((s == "High").sum())),
        weighted_issues=("_weight", "sum"),
    )
    series_per_provider = (
        fact.groupby("provider_code")["specialty_code"].nunique().rename("series")
    )
    merged = providers.merge(
        grouped, left_on="provider_code", right_index=True, how="left"
    ).merge(series_per_provider, left_on="provider_code", right_index=True, how="left")

    counts = ["quality_issues", "high_severity_issues", "weighted_issues"]
    # Cast before filling: the merge introduces object dtype for providers with
    # no issues, and filling an object column is deprecated in pandas.
    merged[counts] = merged[counts].astype("float64").fillna(0.0)
    merged["series"] = merged["series"].fillna(1).clip(lower=1)

    # Penalty proportional to weighted issues per series, capped at 100.
    penalty = (merged["weighted_issues"] / merged["series"] * 25.0).clip(upper=100.0)
    merged["provider_quality_score"] = (100.0 - penalty).round(1)
    return merged.drop(columns=["weighted_issues"])
