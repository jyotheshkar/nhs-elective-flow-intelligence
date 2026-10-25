"""Reproduce portfolio facts and integrity checks from an existing warehouse.

Read-only. Output is technical evidence, not NHS validation or clinical approval.
Usage: python scripts/verify_evidence.py --warehouse data/processed/warehouse.duckdb --output qa/results/warehouse-evidence.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REQUIRED_TABLES = (
    "dim_provider", "dim_specialty", "dim_date", "fact_rtt", "fact_rtt_metrics",
    "fact_forecast", "fact_priority", "fact_quality_issues", "dim_provider_quality",
    "ingestion_audit", "warehouse_metadata",
)


def records(connection, sql, params=None):
    cursor = connection.execute(sql, params or [])
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def json_value(value):
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def inspect_warehouse(connection, expected_source=None):
    """Inspect contents rather than trusting README counts or metadata alone."""
    existing = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    missing = sorted(set(REQUIRED_TABLES) - existing)
    checks = [{"id": "required_tables", "passed": not missing, "detail": missing}]
    counts = {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
              for name in REQUIRED_TABLES if name in existing}
    result = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Independent portfolio technical verification; not clinical validation",
              "table_rows": counts, "checks": checks}
    if missing:
        result["passed"] = False
        return result

    def check(identifier, sql, detail=None):
        violations = int(connection.execute(sql).fetchone()[0])
        checks.append({"id": identifier, "passed": violations == 0,
                       "violations": violations, "detail": detail or ""})

    check("nonempty_facts", "SELECT CASE WHEN COUNT(*)=0 THEN 1 ELSE 0 END FROM fact_rtt")
    check("grain_unique", "SELECT COUNT(*) FROM (SELECT provider_code, specialty_code, reporting_month FROM fact_rtt GROUP BY 1,2,3 HAVING COUNT(*)>1)")
    check("grain_not_null", "SELECT COUNT(*) FROM fact_rtt WHERE provider_code IS NULL OR specialty_code IS NULL OR reporting_month IS NULL")
    check("no_aggregate_specialty", "SELECT COUNT(*) FROM fact_rtt WHERE specialty_code='C_999'", "Total rows would double count specialties")
    check("dimension_provider_unique", "SELECT COUNT(*) FROM (SELECT provider_code FROM dim_provider GROUP BY 1 HAVING COUNT(*)>1)")
    check("dimension_specialty_unique", "SELECT COUNT(*) FROM (SELECT specialty_code FROM dim_specialty GROUP BY 1 HAVING COUNT(*)>1)")
    check("provider_integrity", "SELECT COUNT(*) FROM fact_rtt f LEFT JOIN dim_provider d ON f.provider_code=d.provider_code WHERE d.provider_code IS NULL")
    check("specialty_integrity", "SELECT COUNT(*) FROM fact_rtt f LEFT JOIN dim_specialty d ON f.specialty_code=d.specialty_code WHERE d.specialty_code IS NULL")
    check("date_integrity", "SELECT COUNT(*) FROM fact_rtt f LEFT JOIN dim_date d ON f.reporting_month=d.reporting_month WHERE d.reporting_month IS NULL")
    check("valid_counts", "SELECT COUNT(*) FROM fact_rtt WHERE total_incomplete_pathways<0 OR within_18_weeks<0 OR within_18_weeks>total_incomplete_pathways OR over_52_weeks<0 OR over_52_weeks>total_incomplete_pathways")
    check("valid_source_marker", "SELECT COUNT(*) FROM fact_rtt WHERE data_source_type IS NULL OR data_source_type NOT IN ('OFFICIAL_NHS_PUBLIC','DEMO_SYNTHETIC')")
    sources = records(connection, "SELECT data_source_type,COUNT(*) AS rows FROM fact_rtt GROUP BY 1")
    checks.append({"id": "single_source_mode", "passed": len(sources)==1, "detail": sources})
    if expected_source:
        mismatches = int(connection.execute("SELECT COUNT(*) FROM fact_rtt WHERE data_source_type IS NULL OR data_source_type<>?", [expected_source]).fetchone()[0])
        checks.append({"id": "expected_source", "passed": mismatches==0, "violations": mismatches, "detail": expected_source})
    check("metadata_fact_count", "SELECT COUNT(*) FROM warehouse_metadata WHERE fact_rows<>(SELECT COUNT(*) FROM fact_rtt)")
    check("one_metadata_row", "SELECT CASE WHEN COUNT(*)=1 THEN 0 ELSE 1 END FROM warehouse_metadata")
    check("priority_bounds", "SELECT COUNT(*) FROM fact_priority WHERE priority_score<0 OR priority_score>100")
    latest = records(connection, "SELECT MAX(reporting_month) AS latest_month,MIN(reporting_month) AS earliest_month,COUNT(DISTINCT reporting_month) AS reporting_months,COUNT(DISTINCT provider_code) AS providers,COUNT(DISTINCT specialty_code) AS specialties FROM fact_rtt")[0]
    latest_kpis = records(connection, "SELECT COUNT(*) AS services,SUM(total_incomplete_pathways) AS waiting_pathways,SUM(within_18_weeks) AS within_18_pathways,100.0*SUM(within_18_weeks)/NULLIF(SUM(total_incomplete_pathways),0) AS weighted_within_18_pct,SUM(over_52_weeks) AS over_52_pathways FROM fact_rtt WHERE reporting_month=(SELECT MAX(reporting_month) FROM fact_rtt)")[0]
    result.update({"coverage": latest, "source_modes": sources, "latest_month_kpis": latest_kpis,
                   "metadata": records(connection, "SELECT * FROM warehouse_metadata"),
                   "forecast_models": records(connection, "SELECT forecast_status,forecast_model,COUNT(*) AS series FROM fact_forecast GROUP BY 1,2 ORDER BY 3 DESC"),
                   "forecast_backtest_summary": records(connection, "SELECT COUNT(*) AS forecastable_series,MEDIAN(backtest_mape) AS median_mape_pct,100.0*AVG(CASE WHEN backtest_skill_vs_naive>0 THEN 1.0 WHEN backtest_skill_vs_naive IS NOT NULL THEN 0.0 ELSE NULL END) AS pct_beating_no_change FROM fact_forecast WHERE forecast_status='ok'")[0],
                   "ingestion_status": records(connection, "SELECT processing_status,COUNT(*) AS files FROM ingestion_audit GROUP BY 1"),
                   "caveats": ["Counts are pathways, not unique patients.", "Published aggregate data only; no patient-level validity or outcomes claim.", "One-step model-selection backtests are not independent held-out multi-horizon performance.", "Source publication correctness is outside this technical check.", "A passed integrity check does not establish completeness against every expected source workbook."]})
    result["passed"] = all(item["passed"] for item in checks)
    return json_value(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--warehouse", type=Path, default=Path("data/processed/warehouse.duckdb"))
    parser.add_argument("--expected-source", choices=["OFFICIAL_NHS_PUBLIC", "DEMO_SYNTHETIC"])
    parser.add_argument("--output", type=Path, default=Path("qa/results/warehouse-evidence.json"))
    args = parser.parse_args()
    if not args.warehouse.is_file():
        parser.error(f"Warehouse missing: {args.warehouse}. Build official data or clearly labelled demo first.")
    import duckdb
    connection = duckdb.connect(str(args.warehouse), read_only=True)
    try:
        report = inspect_warehouse(connection, args.expected_source)
    finally:
        connection.close()
    with args.warehouse.open("rb") as stream:
        report["warehouse_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    report["warehouse_file"] = args.warehouse.name
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "output": str(args.output), "coverage": report.get("coverage")}, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
