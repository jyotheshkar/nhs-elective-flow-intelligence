"""Data quality checks over the canonical fact table.

Findings are described as *issues requiring review*, never as errors in the
published data. Public NHS statistics contain legitimate reporting changes,
organisational mergers and genuine step-changes in activity; an automated check
cannot distinguish those from a data problem, and pretending otherwise would be
misleading.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.utils.logging import get_logger
from app.utils.mathx import robust_zscore, safe_divide

logger = get_logger(__name__)

SEVERITY_HIGH = "High"
SEVERITY_MEDIUM = "Medium"
SEVERITY_LOW = "Low"

# A month-on-month move beyond this robust z-score is flagged for review.
ANOMALY_Z_THRESHOLD = 3.5
# Below this absolute change the z-score is ignored: on a 30-pathway list a
# swing of 10 is unremarkable but can look extreme in robust-z terms.
ANOMALY_MIN_ABSOLUTE_CHANGE = 50


@dataclass
class QualityIssue:
    """One data quality finding at a specific grain."""

    provider_code: str | None
    provider_name: str | None
    specialty_code: str | None
    specialty_name: str | None
    month: str | None
    issue_type: str
    severity: str
    description: str
    observed_value: float | None
    expected_value: float | None

    def to_dict(self) -> dict:
        return asdict(self)


def _label_lookup(
    dim_provider: pd.DataFrame, dim_specialty: pd.DataFrame
) -> tuple[dict, dict]:
    providers = dict(
        zip(dim_provider["provider_code"], dim_provider["provider_name"], strict=False)
    )
    specialties = dict(
        zip(dim_specialty["specialty_code"], dim_specialty["specialty_name"], strict=False)
    )
    return providers, specialties


def check_completeness(
    fact: pd.DataFrame,
    dim_provider: pd.DataFrame,
    dim_specialty: pd.DataFrame,
) -> tuple[list[QualityIssue], dict]:
    """Missing values and missing provider x specialty x month combinations."""
    issues: list[QualityIssue] = []
    providers, specialties = _label_lookup(dim_provider, dim_specialty)

    key_measures = ["total_incomplete_pathways", "within_18_weeks"]
    present = fact[key_measures].notna().to_numpy().sum()
    expected = fact[key_measures].size
    value_completeness = float(present / expected * 100.0) if expected else 0.0

    # Panel completeness: a series that reported in an earlier month but is
    # absent later is more interesting than one that never appeared.
    months = sorted(fact["month_key"].dropna().unique())
    observed_pairs = set(
        zip(fact["provider_code"], fact["specialty_code"], strict=False)
    )
    reported = fact.groupby(["provider_code", "specialty_code"])["month_key"].agg(
        ["min", "max", "count"]
    )
    month_index = {m: i for i, m in enumerate(months)}

    gap_count = 0
    for (provider, specialty), row in reported.iterrows():
        first, last, count = row["min"], row["max"], int(row["count"])
        span = month_index[last] - month_index[first] + 1
        if span > count:
            gap_count += span - count
            issues.append(
                QualityIssue(
                    provider_code=provider,
                    provider_name=providers.get(provider),
                    specialty_code=specialty,
                    specialty_name=specialties.get(specialty),
                    month=None,
                    issue_type="Missing reporting months",
                    severity=SEVERITY_MEDIUM if span - count > 1 else SEVERITY_LOW,
                    description=(
                        f"{span - count} reporting month(s) absent between "
                        f"{first} and {last}."
                    ),
                    observed_value=float(count),
                    expected_value=float(span),
                )
            )

    total_possible = len(observed_pairs) * len(months) if months else 0
    panel_completeness = (
        float(len(fact) / total_possible * 100.0) if total_possible else 0.0
    )

    metrics = {
        "value_completeness_pct": round(value_completeness, 2),
        "panel_completeness_pct": round(min(panel_completeness, 100.0), 2),
        "missing_month_gaps": gap_count,
        "reporting_months": len(months),
        "series_count": len(observed_pairs),
    }
    return issues, metrics


def check_consistency(
    fact: pd.DataFrame,
    dim_provider: pd.DataFrame,
    dim_specialty: pd.DataFrame,
) -> tuple[list[QualityIssue], dict]:
    """Duplicates, impossible values and internal contradictions."""
    issues: list[QualityIssue] = []
    providers, specialties = _label_lookup(dim_provider, dim_specialty)
    checked = 0
    failed = 0

    grain = ["provider_code", "specialty_code", "month_key"]
    duplicates = fact[fact.duplicated(subset=grain, keep=False)]
    checked += len(fact)
    failed += len(duplicates)
    for _, row in duplicates.drop_duplicates(subset=grain).iterrows():
        issues.append(
            QualityIssue(
                provider_code=row["provider_code"],
                provider_name=providers.get(row["provider_code"]),
                specialty_code=row["specialty_code"],
                specialty_name=specialties.get(row["specialty_code"]),
                month=row["month_key"],
                issue_type="Duplicate record",
                severity=SEVERITY_HIGH,
                description="More than one row exists at the declared fact grain.",
                observed_value=None,
                expected_value=1.0,
            )
        )

    # Negative counts.
    for column in ("total_incomplete_pathways", "within_18_weeks",
                   "over_52_weeks", "completed_pathways"):
        if column not in fact.columns:
            continue
        values = pd.to_numeric(fact[column], errors="coerce")
        checked += int(values.notna().sum())
        offenders = fact[values < 0]
        failed += len(offenders)
        for _, row in offenders.iterrows():
            issues.append(
                QualityIssue(
                    provider_code=row["provider_code"],
                    provider_name=providers.get(row["provider_code"]),
                    specialty_code=row["specialty_code"],
                    specialty_name=specialties.get(row["specialty_code"]),
                    month=row["month_key"],
                    issue_type="Negative count",
                    severity=SEVERITY_HIGH,
                    description=f"'{column}' is negative, which is not valid.",
                    observed_value=float(row[column]),
                    expected_value=0.0,
                )
            )

    # Part exceeds whole.
    if {"within_18_weeks", "total_incomplete_pathways"} <= set(fact.columns):
        mask = fact["within_18_weeks"] > fact["total_incomplete_pathways"]
        offenders = fact[mask.fillna(False)]
        checked += int(fact["within_18_weeks"].notna().sum())
        failed += len(offenders)
        for _, row in offenders.iterrows():
            issues.append(
                QualityIssue(
                    provider_code=row["provider_code"],
                    provider_name=providers.get(row["provider_code"]),
                    specialty_code=row["specialty_code"],
                    specialty_name=specialties.get(row["specialty_code"]),
                    month=row["month_key"],
                    issue_type="Component exceeds total",
                    severity=SEVERITY_HIGH,
                    description=(
                        "Pathways within 18 weeks exceed total incomplete "
                        "pathways."
                    ),
                    observed_value=float(row["within_18_weeks"]),
                    expected_value=float(row["total_incomplete_pathways"]),
                )
            )

    # Percentages outside range.
    for column in ("pct_within_18_weeks", "pct_over_52_weeks"):
        if column not in fact.columns:
            continue
        values = pd.to_numeric(fact[column], errors="coerce")
        checked += int(values.notna().sum())
        mask = ((values < 0) | (values > 100)).fillna(False)
        offenders = fact[mask]
        failed += len(offenders)
        for _, row in offenders.iterrows():
            issues.append(
                QualityIssue(
                    provider_code=row["provider_code"],
                    provider_name=providers.get(row["provider_code"]),
                    specialty_code=row["specialty_code"],
                    specialty_name=specialties.get(row["specialty_code"]),
                    month=row["month_key"],
                    issue_type="Percentage out of range",
                    severity=SEVERITY_HIGH,
                    description=f"'{column}' sits outside 0-100.",
                    observed_value=float(row[column]),
                    expected_value=None,
                )
            )

    # Reconciliation: our recomputed 18-week percentage against the published
    # one. A mismatch means our derivation has drifted from the source.
    if {"pct_within_18_weeks", "pct_within_18_weeks_source"} <= set(fact.columns):
        derived = pd.to_numeric(fact["pct_within_18_weeks"], errors="coerce")
        published = pd.to_numeric(fact["pct_within_18_weeks_source"], errors="coerce")
        difference = (derived - published).abs()
        mask = (difference > 0.5).fillna(False)
        offenders = fact[mask]
        checked += int(difference.notna().sum())
        failed += len(offenders)
        for _, row in offenders.head(200).iterrows():
            issues.append(
                QualityIssue(
                    provider_code=row["provider_code"],
                    provider_name=providers.get(row["provider_code"]),
                    specialty_code=row["specialty_code"],
                    specialty_name=specialties.get(row["specialty_code"]),
                    month=row["month_key"],
                    issue_type="Derivation mismatch",
                    severity=SEVERITY_MEDIUM,
                    description=(
                        "Recomputed % within 18 weeks differs from the "
                        "published value by more than 0.5 percentage points."
                    ),
                    observed_value=round(float(row["pct_within_18_weeks"]), 2),
                    expected_value=round(
                        float(row["pct_within_18_weeks_source"]), 2
                    ),
                )
            )

    consistency_pct = (
        float((checked - failed) / checked * 100.0) if checked else 100.0
    )
    metrics = {
        "consistency_pct": round(max(0.0, consistency_pct), 2),
        "checks_run": checked,
        "checks_failed": failed,
    }
    return issues, metrics


def check_freshness(fact: pd.DataFrame) -> tuple[list[QualityIssue], dict]:
    """Age of the most recent reporting period.

    NHS England publishes RTT roughly six to eight weeks after month end, so a
    two-month lag is normal and is scored as fully fresh.
    """
    if fact.empty:
        return [], {"freshness_pct": 0.0, "latest_month": None, "lag_months": None}

    latest = pd.Timestamp(fact["reporting_month"].max())
    now = pd.Timestamp(datetime.now(UTC).date())
    lag_months = (now.year - latest.year) * 12 + (now.month - latest.month)

    # Full marks up to a 2-month lag; then 15 points per further month.
    freshness = float(np.clip(100.0 - max(0, lag_months - 2) * 15.0, 0.0, 100.0))

    issues: list[QualityIssue] = []
    if lag_months > 4:
        issues.append(
            QualityIssue(
                provider_code=None,
                provider_name=None,
                specialty_code=None,
                specialty_name=None,
                month=latest.strftime("%Y-%m"),
                issue_type="Stale data",
                severity=SEVERITY_MEDIUM if lag_months <= 6 else SEVERITY_HIGH,
                description=(
                    f"The most recent loaded reporting period is {lag_months} "
                    "months old. Re-run ingestion to pick up newer "
                    "publications."
                ),
                observed_value=float(lag_months),
                expected_value=2.0,
            )
        )

    return issues, {
        "freshness_pct": round(freshness, 2),
        "latest_month": latest.strftime("%Y-%m"),
        "latest_month_label": latest.strftime("%B %Y"),
        "lag_months": int(lag_months),
    }


def check_anomalies(
    fact: pd.DataFrame,
    dim_provider: pd.DataFrame,
    dim_specialty: pd.DataFrame,
) -> tuple[list[QualityIssue], dict]:
    """Unusual month-on-month movements, flagged for review not correction."""
    issues: list[QualityIssue] = []
    providers, specialties = _label_lookup(dim_provider, dim_specialty)

    df = fact.sort_values(["provider_code", "specialty_code", "reporting_month"]).copy()
    df["_change"] = df.groupby(["provider_code", "specialty_code"])[
        "total_incomplete_pathways"
    ].diff()
    df["_z"] = df.groupby(["provider_code", "specialty_code"])["_change"].transform(
        robust_zscore
    )
    df["_pct"] = safe_divide(
        df["_change"],
        df.groupby(["provider_code", "specialty_code"])[
            "total_incomplete_pathways"
        ].shift(1),
    ) * 100.0

    flagged = df[
        (df["_z"].abs() > ANOMALY_Z_THRESHOLD)
        & (df["_change"].abs() >= ANOMALY_MIN_ABSOLUTE_CHANGE)
    ]

    for _, row in flagged.iterrows():
        direction = "increase" if row["_change"] > 0 else "decrease"
        magnitude = abs(float(row["_z"]))
        issues.append(
            QualityIssue(
                provider_code=row["provider_code"],
                provider_name=providers.get(row["provider_code"]),
                specialty_code=row["specialty_code"],
                specialty_name=specialties.get(row["specialty_code"]),
                month=row["month_key"],
                issue_type="Unusual month-on-month change",
                severity=SEVERITY_MEDIUM if magnitude < 6 else SEVERITY_HIGH,
                description=(
                    f"Waiting list {direction} of "
                    f"{abs(float(row['_change'])):,.0f} pathways "
                    f"({float(row['_pct']):+.1f}%), "
                    f"{magnitude:.1f} robust standard deviations from this "
                    "series' typical movement. May reflect a genuine "
                    "operational change, a reporting change or a data issue."
                ),
                observed_value=round(float(row["total_incomplete_pathways"]), 0),
                expected_value=(
                    round(
                        float(row["total_incomplete_pathways"] - row["_change"]), 0
                    )
                ),
            )
        )

    observations = int(df["_change"].notna().sum())
    anomaly_rate = (
        float(len(flagged) / observations * 100.0) if observations else 0.0
    )
    # Anomaly burden score: 0% anomalies -> 100, 5% or more -> 0.
    burden_score = float(np.clip(100.0 - anomaly_rate * 20.0, 0.0, 100.0))

    return issues, {
        "anomaly_count": len(flagged),
        "anomaly_rate_pct": round(anomaly_rate, 3),
        "anomaly_burden_score": round(burden_score, 2),
        "observations_tested": observations,
    }
