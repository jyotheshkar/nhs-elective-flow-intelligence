"""Materialise the DuckDB warehouse from committed Parquet artefacts.

Deployment support script. The repository ships the *processed* analytical
layer (Parquet files in ``data/processed``) but not the DuckDB file itself,
because DuckDB storage is version-sensitive and the Parquet layer is the
durable artefact. On an ephemeral-filesystem host (for example a Render free
web service) this script runs during the build step and recreates the
warehouse deterministically in a few seconds - no network access, no source
downloads and no recomputation are required.

Usage::

    python scripts/materialise_warehouse.py

Exits non-zero if the required Parquet artefacts are missing, so a broken
deploy fails at build time rather than serving 503s at runtime.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.utils.logging import configure_logging, get_logger

logger = get_logger("scripts.materialise_warehouse")

# The parquet artefacts the API depends on. Mirrors the build output of
# scripts/build_warehouse.py; anything missing is a hard failure.
REQUIRED_TABLES = (
    "dim_provider",
    "dim_specialty",
    "dim_date",
    "fact_rtt",
    "fact_rtt_metrics",
    "fact_forecast",
    "fact_priority",
    "fact_quality_issues",
    "dim_provider_quality",
    "ingestion_audit",
    "warehouse_metadata",
)


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)

    import duckdb  # noqa: PLC0415

    from app.database.warehouse import SQL_DIR  # noqa: PLC0415

    processed = settings.processed_dir
    missing = [
        name for name in REQUIRED_TABLES
        if not (processed / f"{name}.parquet").exists()
    ]
    if missing:
        logger.error(
            "Cannot materialise the warehouse: missing Parquet artefacts %s "
            "in %s. Run 'python scripts/build_warehouse.py' first (or commit "
            "the processed layer before deploying).",
            missing, processed,
        )
        return 1

    target = settings.warehouse_path
    if target.exists():
        target.unlink()

    connection = duckdb.connect(str(target))
    try:
        for name in REQUIRED_TABLES:
            path = (processed / f"{name}.parquet").as_posix()
            connection.execute(
                f"CREATE OR REPLACE TABLE {name} AS "
                f"SELECT * FROM read_parquet('{path}')"
            )
        connection.execute((SQL_DIR / "views.sql").read_text(encoding="utf-8"))
        connection.execute("CHECKPOINT")
        counts = {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in REQUIRED_TABLES
        }
    finally:
        connection.close()

    logger.info("Warehouse materialised at %s", target)
    for name, count in counts.items():
        logger.info("  %-24s %10s rows", name, f"{count:,}")
    print(f"OK: warehouse materialised from Parquet at {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
