"""Schema and integrity validation applied between extract and transform.

Validation is deliberately *loud but non-fatal* for row-level issues: a single
provider publishing an implausible value should be surfaced on the data quality
page rather than aborting the pipeline. Structural problems (missing key
columns, empty frames) are fatal, because everything downstream depends on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from app.transformation.schema import (
    NON_NEGATIVE_MEASURES,
    PERCENTAGE_FIELDS,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    """One validation finding."""

    check: str
    severity: str        # "error" | "warning" | "info"
    message: str
    row_count: int = 0


@dataclass
class ValidationReport:
    """Aggregate result of validating one frame."""

    dataset: str
    passed: bool
    row_count: int
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def summary(self) -> str:
        return (
            f"{self.dataset}: {self.row_count} rows, "
            f"{len(self.errors)} errors, {len(self.warnings)} warnings"
        )


def validate_raw_frame(
    frame: pd.DataFrame,
    dataset: str,
    required_columns: tuple[str, ...],
) -> ValidationReport:
    """Validate a parsed workbook frame before it enters the canonical model."""
    issues: list[ValidationIssue] = []
    passed = True

    if frame.empty:
        return ValidationReport(
            dataset=dataset,
            passed=False,
            row_count=0,
            issues=[ValidationIssue("non_empty", "error", "Frame contains no rows.")],
        )

    missing = [c for c in required_columns if c not in frame.columns]
    if missing:
        passed = False
        issues.append(
            ValidationIssue(
                "required_columns",
                "error",
                f"Missing required columns: {missing}",
            )
        )

    # Duplicate grain: the same provider x specialty appearing twice in one
    # month means the file contains an unexpected extra section.
    grain = [c for c in ("provider_code", "specialty_code") if c in frame.columns]
    if grain:
        duplicates = int(frame.duplicated(subset=grain).sum())
        if duplicates:
            issues.append(
                ValidationIssue(
                    "duplicate_grain",
                    "warning",
                    f"{duplicates} duplicate provider x specialty rows found; "
                    "the last occurrence will be retained.",
                    duplicates,
                )
            )

    for column in NON_NEGATIVE_MEASURES:
        if column in frame.columns:
            negatives = int((frame[column] < 0).sum())
            if negatives:
                issues.append(
                    ValidationIssue(
                        f"non_negative::{column}",
                        "warning",
                        f"{negatives} negative values in '{column}'.",
                        negatives,
                    )
                )

    # Part cannot exceed whole.
    if {"within_18_weeks", "total_incomplete_pathways"} <= set(frame.columns):
        breaches = int(
            (frame["within_18_weeks"] > frame["total_incomplete_pathways"]).sum()
        )
        if breaches:
            issues.append(
                ValidationIssue(
                    "within_18_le_total",
                    "warning",
                    f"{breaches} rows where 'within 18 weeks' exceeds the total "
                    "incomplete pathways.",
                    breaches,
                )
            )

    # Long-wait bands must nest: 52+ >= 65+ >= 78+ >= 104+.
    nesting = [
        ("over_52_weeks", "over_65_weeks"),
        ("over_65_weeks", "over_78_weeks"),
        ("over_78_weeks", "over_104_weeks"),
    ]
    for wider, narrower in nesting:
        if {wider, narrower} <= set(frame.columns):
            breaches = int((frame[narrower] > frame[wider]).sum())
            if breaches:
                issues.append(
                    ValidationIssue(
                        f"band_nesting::{wider}>={narrower}",
                        "warning",
                        f"{breaches} rows where '{narrower}' exceeds '{wider}'.",
                        breaches,
                    )
                )

    for column in PERCENTAGE_FIELDS:
        if column in frame.columns:
            out_of_range = int(
                ((frame[column] < 0) | (frame[column] > 100)).sum()
            )
            if out_of_range:
                issues.append(
                    ValidationIssue(
                        f"percentage_range::{column}",
                        "warning",
                        f"{out_of_range} values outside 0-100 in '{column}'.",
                        out_of_range,
                    )
                )

    report = ValidationReport(
        dataset=dataset, passed=passed, row_count=len(frame), issues=issues
    )
    logger.info("Validation %s", report.summary())
    for issue in report.issues:
        log = logger.error if issue.severity == "error" else logger.warning
        log("  [%s] %s", issue.check, issue.message)
    return report


def validate_canonical_fact(frame: pd.DataFrame) -> ValidationReport:
    """Final gate on the canonical fact table before it is persisted."""
    issues: list[ValidationIssue] = []
    passed = True

    required = ("provider_code", "specialty_code", "reporting_month",
                "total_incomplete_pathways")
    missing = [c for c in required if c not in frame.columns]
    if missing:
        passed = False
        issues.append(
            ValidationIssue("fact_columns", "error", f"Missing: {missing}")
        )
        return ValidationReport("fact_rtt", False, len(frame), issues)

    duplicates = int(
        frame.duplicated(
            subset=["provider_code", "specialty_code", "reporting_month"]
        ).sum()
    )
    if duplicates:
        passed = False
        issues.append(
            ValidationIssue(
                "fact_grain_unique",
                "error",
                f"{duplicates} duplicate rows at the declared fact grain "
                "(provider x specialty x month).",
                duplicates,
            )
        )

    if frame["total_incomplete_pathways"].isna().all():
        passed = False
        issues.append(
            ValidationIssue(
                "waiting_list_populated",
                "error",
                "Every waiting-list value is null.",
            )
        )

    report = ValidationReport("fact_rtt", passed, len(frame), issues)
    logger.info("Validation %s", report.summary())
    return report
