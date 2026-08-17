"""DuckDB analytical warehouse.

Parquet is the storage format and DuckDB is the query engine. Together they give
an analytical warehouse with zero server configuration, which keeps the project
genuinely reproducible on a laptop.

The warehouse is built once by ``scripts/build_warehouse.py`` and read
read-only by the API. Analytical aggregation happens in SQL, not in the
frontend.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Physical tables materialised into the warehouse.
TABLES = (
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

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def _read_sql(name: str) -> str:
    path = SQL_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    return path.read_text(encoding="utf-8")


def build_warehouse(frames: dict[str, pd.DataFrame]) -> Path:
    """Write ``frames`` to Parquet and materialise the DuckDB warehouse."""
    settings = get_settings()
    settings.ensure_directories()
    processed = settings.processed_dir
    target = settings.warehouse_path

    # Parquet is the durable artefact; DuckDB is rebuilt from it.
    for name, frame in frames.items():
        path = processed / f"{name}.parquet"
        frame.to_parquet(path, index=False)
        logger.info("Wrote %s (%d rows) -> %s", name, len(frame), path.name)

    if target.exists():
        target.unlink()

    connection = duckdb.connect(str(target))
    try:
        for name in frames:
            path = (processed / f"{name}.parquet").as_posix()
            connection.execute(
                f"CREATE OR REPLACE TABLE {name} AS "
                f"SELECT * FROM read_parquet('{path}')"
            )
        connection.execute(_read_sql("views.sql"))
        connection.execute("CHECKPOINT")
        counts = {
            name: connection.execute(
                f"SELECT COUNT(*) FROM {name}"
            ).fetchone()[0]
            for name in frames
        }
        logger.info("Warehouse built at %s: %s", target, counts)
    finally:
        connection.close()

    return target


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Open a connection to the warehouse."""
    settings = get_settings()
    path = settings.warehouse_path
    if not path.exists():
        raise FileNotFoundError(
            f"Warehouse not found at {path}. Build it with: make data"
        )
    return duckdb.connect(str(path), read_only=read_only)


def warehouse_exists() -> bool:
    """True when a built warehouse is available."""
    return get_settings().warehouse_path.exists()


def query(sql: str, params: list | dict | None = None) -> pd.DataFrame:
    """Run a read-only query against the warehouse and return a DataFrame."""
    connection = connect(read_only=True)
    try:
        if params:
            return connection.execute(sql, params).df()
        return connection.execute(sql).df()
    finally:
        connection.close()


def table_row_counts() -> dict[str, int]:
    """Row count per table, used by the health endpoint."""
    connection = connect(read_only=True)
    try:
        existing = {
            row[0]
            for row in connection.execute("SHOW TABLES").fetchall()
        }
        return {
            name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in TABLES
            if name in existing
        }
    finally:
        connection.close()
