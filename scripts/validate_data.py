"""Validate the built warehouse and print a data quality report.

Usage
-----
    python scripts/validate_data.py
    python scripts/validate_data.py --issues 25
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.utils.logging import configure_logging, get_logger

logger = get_logger("scripts.validate_data")


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--issues", type=int, default=15, help="Number of issues to display."
    )
    args = parser.parse_args()

    from app.database import warehouse

    if not warehouse.warehouse_exists():
        print("No warehouse found. Build one first:")
        print("    python scripts/build_warehouse.py        # official data")
        print("    python scripts/build_warehouse.py --demo # synthetic data")
        return 1

    from app.quality.score import build_quality_report
    from app.transformation.validation import validate_canonical_fact

    fact = warehouse.query("SELECT * FROM fact_rtt")
    dim_provider = warehouse.query("SELECT * FROM dim_provider")
    dim_specialty = warehouse.query("SELECT * FROM dim_specialty")
    metadata = warehouse.query("SELECT * FROM warehouse_metadata LIMIT 1")
    audit = warehouse.query("SELECT * FROM ingestion_audit")

    print()
    print("=" * 74)
    print("  WAREHOUSE VALIDATION")
    print("=" * 74)

    if not metadata.empty:
        row = metadata.iloc[0]
        print(f"  Data source type   : {row['data_source_type']}")
        print(f"  Latest month       : {row['latest_reporting_month']}")
        print(f"  Reporting months   : {row['reporting_months']}")
        print(f"  Providers          : {row['provider_count']}")
        print(f"  Specialties        : {row['specialty_count']}")
        print(f"  Fact rows          : {row['fact_rows']:,}")
        print(f"  Built at           : {row['built_at']}")

    print()
    print("  --- Ingestion audit ---")
    if audit.empty:
        print("  (no audit records)")
    else:
        by_status = audit["processing_status"].value_counts().to_dict()
        for status, count in by_status.items():
            print(f"  {status:<22} {count:>5}")
        failed = audit[audit["processing_status"] != "processed"]
        for _, item in failed.head(10).iterrows():
            print(f"    ! {item['source_file']}: {item['message']}")

    print()
    print("  --- Schema validation ---")
    report = validate_canonical_fact(fact)
    print(f"  Passed             : {report.passed}")
    print(f"  Errors             : {len(report.errors)}")
    print(f"  Warnings           : {len(report.warnings)}")
    for issue in report.issues[:10]:
        print(f"    [{issue.severity}] {issue.check}: {issue.message}")

    print()
    print("  --- Data quality ---")
    quality = build_quality_report(fact, dim_provider, dim_specialty)
    print(f"  Overall score      : {quality.overall_score}/100")
    for key, score in quality.dimension_scores.items():
        contribution = quality.dimension_contributions[key]
        print(f"    {key:<18} {score:>6.2f}/100  -> {contribution:>5.2f} points")

    print()
    print(f"  Total issues       : {len(quality.issues)}")
    severities: dict[str, int] = {}
    for issue in quality.issues:
        severities[issue.severity] = severities.get(issue.severity, 0) + 1
    for severity, count in sorted(severities.items()):
        print(f"    {severity:<18} {count:>5}")

    if quality.issues:
        print()
        print(f"  --- Top {args.issues} issues ---")
        for issue in quality.issues[: args.issues]:
            scope = " / ".join(
                p for p in (issue.provider_name, issue.specialty_name, issue.month) if p
            )
            print(f"  [{issue.severity:<6}] {issue.issue_type}")
            print(f"           {scope}")
            print(f"           {issue.description}")

    print("=" * 74)
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
