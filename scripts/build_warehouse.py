"""Build the DuckDB analytical warehouse.

Runs the full pipeline: ingest official NHS England files (or load the demo
dataset), derive metrics, forecast, score priority, run data quality checks and
materialise Parquet + DuckDB.

Usage
-----
    python scripts/build_warehouse.py                 # official data, 18 months
    python scripts/build_warehouse.py --months 24     # longer window
    python scripts/build_warehouse.py --demo          # synthetic demo dataset
    python scripts/build_warehouse.py --offline       # reuse files in data/raw
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.utils.logging import configure_logging, get_logger

logger = get_logger("scripts.build_warehouse")


def _discover_local_files(months: int):
    """Find already-downloaded workbooks in ``data/raw`` for offline builds."""
    import re  # noqa: PLC0415

    import pandas as pd  # noqa: PLC0415

    from app.ingestion.discovery import _parse_reporting_month, _parse_revision  # noqa: PLC0415

    settings = get_settings()
    found: dict[tuple[str, str], tuple[int, str, pd.Timestamp]] = {}

    for dataset in ("incomplete", "admitted", "non_admitted"):
        directory = settings.raw_dir / dataset
        if not directory.exists():
            continue
        for path in directory.glob("*.xlsx"):
            match = re.search(r"([A-Za-z]{3})(\d{2})", path.name)
            if not match:
                continue
            month = _parse_reporting_month(match.group(1), match.group(2))
            if month is None:
                continue
            key = (dataset, month.strftime("%Y-%m"))
            revision = _parse_revision(path.name)
            incumbent = found.get(key)
            if incumbent is None or revision > incumbent[0]:
                found[key] = (revision, str(path), pd.Timestamp(month))

    incomplete_months = sorted(
        {m for (ds, m) in found if ds == "incomplete"}, reverse=True
    )[:months]
    keep = set(incomplete_months)
    return [
        (path, dataset, month)
        for (dataset, month_key), (_rev, path, month) in sorted(found.items())
        if month_key in keep
    ]


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--months", type=int, default=settings.ingest_months)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Build from the clearly-labelled synthetic demo dataset.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Build from workbooks already present in data/raw.",
    )
    parser.add_argument("--force-download", action="store_true")
    args = parser.parse_args()

    from app.database.builder import build_all  # noqa: PLC0415

    if args.demo:
        logger.info("Building warehouse from DEMO SYNTHETIC data")
        from seed_demo import build_demo_dataset  # noqa: PLC0415

        result = build_demo_dataset()
        build = build_all(
            fact=result.fact,
            dim_provider=result.dim_provider,
            dim_specialty=result.dim_specialty,
            dim_date=result.dim_date,
            audit=result.audit,
            messages=[
                "DEMO SYNTHETIC DATA - illustrative only. These figures are "
                "generated, not published NHS England statistics."
            ],
        )
    else:
        from app.ingestion.pipeline import ingest_local_files, run_ingestion  # noqa: PLC0415

        if args.offline:
            local = _discover_local_files(args.months)
            if not local:
                logger.error(
                    "No workbooks found in %s. Run: python scripts/download_data.py",
                    settings.raw_dir,
                )
                return 1
            logger.info("Offline build from %d local workbooks", len(local))
            ingestion = ingest_local_files(local)
        else:
            ingestion = run_ingestion(
                months=args.months, force_download=args.force_download
            )

        build = build_all(
            fact=ingestion.fact,
            dim_provider=ingestion.dim_provider,
            dim_specialty=ingestion.dim_specialty,
            dim_date=ingestion.dim_date,
            audit=ingestion.audit,
            messages=ingestion.messages,
        )

    print()
    print("=" * 70)
    print("  WAREHOUSE BUILD COMPLETE")
    print("=" * 70)
    print(f"  Location            : {build.warehouse_path}")
    print(f"  Data source type    : {build.data_source_type}")
    print(f"  Latest month        : {build.latest_month}")
    print(f"  Reporting months    : {build.reporting_months}")
    print(f"  Data quality score  : {build.quality_score}/100")
    print(
        f"  Forecasts           : {build.forecast_summary['series_forecast']} series"
        f" (median MAPE {build.forecast_summary['median_mape']}%)"
    )
    print(
        f"  Beating naive       : "
        f"{build.forecast_summary['share_beating_naive']}% of series"
    )
    print("  Table row counts    :")
    for name, count in build.row_counts.items():
        print(f"      {name:<24} {count:>10,}")
    if build.messages:
        print("  Notes:")
        for message in build.messages:
            print(f"      - {message}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
