"""Export a validated, read-only DuckDB snapshot for Power BI or Excel.

Run from repository root:
    python scripts/export_bi.py --warehouse data/warehouse.duckdb --output bi/export
The output is public aggregate statistics or clearly labelled synthetic data.
No Power BI Desktop automation or PBIX validation is implied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

TABLE_COLUMNS = {
    "dim_provider": ["provider_code", "provider_name", "region_name"],
    "dim_specialty": ["specialty_code", "specialty_name", "specialty_group"],
    "dim_date": ["reporting_month", "month_key", "financial_year", "quarter"],
    "fact_rtt": [
        "provider_code", "specialty_code", "reporting_month", "data_source_type",
        "total_incomplete_pathways", "within_18_weeks", "over_52_weeks",
        "completed_pathways",
    ],
    "fact_priority": [
        "provider_code", "specialty_code", "reporting_month", "data_source_type",
        "priority_score", "priority_band", "is_rankable",
    ],
    "warehouse_metadata": [
        "built_at", "data_source_type", "latest_reporting_month", "fact_rows",
        "quality_score", "referral_to_treatment_benchmark",
    ],
}
KEYS = {
    "dim_provider": ["provider_code"],
    "dim_specialty": ["specialty_code"],
    "dim_date": ["reporting_month"],
    "fact_rtt": ["provider_code", "specialty_code", "reporting_month"],
    "fact_priority": ["provider_code", "specialty_code", "reporting_month"],
}


def _validate(connection) -> dict:
    for table, columns in TABLE_COLUMNS.items():
        # Identifiers are constants declared above, never command-line strings.
        actual = {row[0] for row in connection.execute(f"DESCRIBE {table}").fetchall()}
        missing = set(columns) - actual
        if missing:
            raise ValueError(f"{table}: missing columns {sorted(missing)}")
    for table, keys in KEYS.items():
        key_sql = ", ".join(keys)
        if connection.execute(
            f"SELECT COUNT(*) FROM (SELECT {key_sql} FROM {table} "
            f"GROUP BY {key_sql} HAVING COUNT(*) > 1)"
        ).fetchone()[0]:
            raise ValueError(f"{table}: duplicate analytical grain")
        null_check = " OR ".join(f"{key} IS NULL" for key in keys)
        if connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {null_check}"
        ).fetchone()[0]:
            raise ValueError(f"{table}: null relationship key")
    for fact in ("fact_rtt", "fact_priority"):
        for dimension, key in (
            ("dim_provider", "provider_code"), ("dim_specialty", "specialty_code"),
            ("dim_date", "reporting_month"),
        ):
            if connection.execute(
                f"SELECT COUNT(*) FROM {fact} f LEFT JOIN {dimension} d "
                f"ON f.{key}=d.{key} WHERE d.{key} IS NULL"
            ).fetchone()[0]:
                raise ValueError(f"{fact}: orphan {key}")
        if connection.execute(
            f"SELECT COUNT(*) FROM {fact} WHERE specialty_code='C_999'"
        ).fetchone()[0]:
            raise ValueError(f"{fact}: C_999 total would double count specialties")
    for table in ("dim_date", "fact_rtt", "fact_priority"):
        if connection.execute(
            f"SELECT COUNT(*) FROM {table} "
            "WHERE reporting_month != date_trunc('month', reporting_month)"
        ).fetchone()[0]:
            raise ValueError(f"{table}: reporting_month must be month start")
    if connection.execute(
        "SELECT COUNT(*) FROM fact_rtt WHERE total_incomplete_pathways < 0 "
        "OR within_18_weeks < 0 OR over_52_weeks < 0 OR completed_pathways < 0 "
        "OR within_18_weeks > total_incomplete_pathways "
        "OR over_52_weeks > total_incomplete_pathways"
    ).fetchone()[0]:
        raise ValueError("fact_rtt: invalid count bounds")
    source_rows = connection.execute(
        "SELECT DISTINCT data_source_type FROM fact_rtt"
    ).fetchall()
    if len(source_rows) != 1 or source_rows[0][0] not in (
        "OFFICIAL_NHS_PUBLIC", "DEMO_SYNTHETIC"
    ):
        raise ValueError("Export requires exactly one recognised data source type")
    source = source_rows[0][0]
    if connection.execute("SELECT COUNT(*) FROM warehouse_metadata").fetchone()[0] != 1:
        raise ValueError("warehouse_metadata must contain one build record")
    metadata_source, metadata_rows, metadata_month = connection.execute(
        "SELECT data_source_type, fact_rows, latest_reporting_month "
        "FROM warehouse_metadata"
    ).fetchone()
    latest = connection.execute("SELECT MAX(reporting_month) FROM fact_rtt").fetchone()[0]
    fact_rows = connection.execute("SELECT COUNT(*) FROM fact_rtt").fetchone()[0]
    if metadata_source != source or metadata_rows != fact_rows:
        raise ValueError("Build metadata does not reconcile to fact rows/source")
    if str(metadata_month)[:7] != str(latest)[:7]:
        raise ValueError("Build metadata reporting period does not reconcile")
    if connection.execute(
        "SELECT COUNT(*) FROM fact_priority "
        "WHERE data_source_type != ? OR reporting_month != ?",
        [source, latest],
    ).fetchone()[0]:
        raise ValueError("Priority table must match latest month and source")
    total, within, denominator, missing = connection.execute(
        "SELECT SUM(total_incomplete_pathways), "
        "SUM(CASE WHEN within_18_weeks IS NOT NULL "
        "AND total_incomplete_pathways > 0 THEN within_18_weeks END), "
        "SUM(CASE WHEN within_18_weeks IS NOT NULL "
        "AND total_incomplete_pathways > 0 THEN total_incomplete_pathways END), "
        "COUNT(*) FILTER (WHERE within_18_weeks IS NULL "
        "OR total_incomplete_pathways IS NULL) "
        "FROM fact_rtt WHERE reporting_month=?", [latest],
    ).fetchone()
    total = float(total) if total is not None else None
    within = float(within) if within is not None else None
    denominator = float(denominator) if denominator is not None else None
    return {
        "data_source_type": source,
        "latest_reporting_month": str(latest)[:10],
        "latest_waiting_list": total,
        "latest_18week_numerator_complete_pairs": within,
        "latest_18week_denominator_complete_pairs": denominator,
        "latest_pct_within_18_complete_pairs": (
            100 * within / denominator if within is not None and denominator else None
        ),
        "latest_rows_with_missing_18week_counts": missing,
        "fact_rows": fact_rows,
    }


def export_bi(warehouse: Path, output: Path) -> dict:
    """Validate the entire snapshot before changing any existing export."""
    import duckdb

    warehouse = Path(warehouse).resolve()
    output = Path(output).resolve()
    if not warehouse.is_file():
        raise FileNotFoundError(f"Build or materialise the warehouse first: {warehouse}")
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        controls = _validate(connection)
        output.mkdir(parents=True, exist_ok=True)
        manifest = {
            "exported_at_utc": datetime.now(UTC).isoformat(),
            "warehouse": warehouse.name,
            "controls": controls,
            "files": {},
            "warning": "Independent portfolio prototype. Not an NHS operational system.",
        }
        # A failed validation never replaces previous files. Manifest is published last.
        with tempfile.TemporaryDirectory(prefix="bi-stage-", dir=output) as stage:
            for table, columns in TABLE_COLUMNS.items():
                frame = connection.execute(
                    f"SELECT {', '.join(columns)} FROM {table}"
                ).df()
                if "reporting_month" in frame.columns:
                    frame["reporting_month"] = frame["reporting_month"].dt.strftime(
                        "%Y-%m-%d"
                    )
                path = Path(stage) / f"{table}.csv"
                frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
                manifest["files"][path.name] = {
                    "rows": len(frame),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "columns": columns,
                }
            for filename in manifest["files"]:
                os.replace(Path(stage) / filename, output / filename)
            manifest_path = Path(stage) / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            os.replace(manifest_path, output / "manifest.json")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("bi/export"))
    args = parser.parse_args()
    print(json.dumps(export_bi(args.warehouse, args.output), indent=2))


if __name__ == "__main__":
    main()
