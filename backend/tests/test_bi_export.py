"""Acceptance checks for the downstream BI export and reporting controls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_bi.py"
_SPEC = importlib.util.spec_from_file_location("export_bi", _MODULE_PATH)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
export_bi = _MODULE.export_bi


@pytest.fixture
def bi_warehouse(tmp_path):
    path = tmp_path / "test.duckdb"
    with duckdb.connect(str(path)) as db:
        db.execute("""
            CREATE TABLE dim_provider AS SELECT 'P1' provider_code,
                'Synthetic Provider' provider_name, 'Synthetic Region' region_name;
            CREATE TABLE dim_specialty AS SELECT 'S1' specialty_code,
                'Synthetic Specialty 1' specialty_name, 'Other' specialty_group
                UNION ALL SELECT 'S2', 'Synthetic Specialty 2', 'Other'
                UNION ALL SELECT 'S3', 'Synthetic Specialty 3', 'Other';
            CREATE TABLE dim_date AS SELECT DATE '2026-01-01' reporting_month,
                '2026-01' month_key, '2025/26' financial_year, 'Q1' AS "quarter";
            CREATE TABLE fact_rtt AS
                SELECT 'P1' provider_code, 'S1' specialty_code,
                    DATE '2026-01-01' reporting_month, 'DEMO_SYNTHETIC' data_source_type,
                    1000.0 total_incomplete_pathways, 900.0 within_18_weeks,
                    10.0 over_52_weeks, 100.0 completed_pathways
                UNION ALL SELECT 'P1', 'S2', DATE '2026-01-01',
                    'DEMO_SYNTHETIC', 100.0, 10.0, 20.0, 10.0
                UNION ALL SELECT 'P1', 'S3', DATE '2026-01-01',
                    'DEMO_SYNTHETIC', 200.0, NULL, 10.0, NULL;
            CREATE TABLE fact_priority AS SELECT 'P1' provider_code,
                'S1' specialty_code, DATE '2026-01-01' reporting_month,
                'DEMO_SYNTHETIC' data_source_type, 70.0 priority_score,
                'HIGH' priority_band, TRUE is_rankable;
            CREATE TABLE warehouse_metadata AS SELECT '2026-10-24T00:00:00Z' built_at,
                'DEMO_SYNTHETIC' data_source_type, '2026-01' latest_reporting_month,
                3 fact_rows, 95.0 quality_score, 92.0 referral_to_treatment_benchmark;
        """)
    return path


def test_export_reconciles_weighted_rate_and_missing_coverage(bi_warehouse, tmp_path):
    output = tmp_path / "export"
    result = export_bi(bi_warehouse, output)
    controls = result["controls"]
    assert controls["latest_waiting_list"] == 1300
    assert controls["latest_18week_denominator_complete_pairs"] == 1100
    assert controls["latest_pct_within_18_complete_pairs"] == pytest.approx(910 / 1100 * 100)
    assert controls["latest_pct_within_18_complete_pairs"] != 50
    assert controls["latest_rows_with_missing_18week_counts"] == 1
    assert controls["data_source_type"] == "DEMO_SYNTHETIC"
    assert set(result["files"]) == {
        "dim_provider.csv", "dim_specialty.csv", "dim_date.csv",
        "fact_rtt.csv", "fact_priority.csv", "warehouse_metadata.csv",
    }
    fact = pd.read_csv(output / "fact_rtt.csv")
    assert fact.reporting_month.unique().tolist() == ["2026-01-01"]
    assert fact.within_18_weeks.isna().sum() == 1
    assert json.loads((output / "manifest.json").read_text()) == result


@pytest.mark.parametrize("mutation, message", [
    ("INSERT INTO fact_rtt SELECT * FROM fact_rtt LIMIT 1", "duplicate analytical grain"),
    ("UPDATE fact_rtt SET provider_code='MISSING'", "orphan provider_code"),
    ("UPDATE fact_rtt SET specialty_code='C_999' WHERE specialty_code='S1'; "
     "INSERT INTO dim_specialty VALUES ('C_999','Total','Other')", "double count"),
    ("UPDATE fact_rtt SET data_source_type='OFFICIAL_NHS_PUBLIC' "
     "WHERE specialty_code='S1'", "one recognised data source type"),
    ("UPDATE warehouse_metadata SET fact_rows=123", "does not reconcile"),
    ("UPDATE fact_rtt SET within_18_weeks=999 WHERE specialty_code='S2'", "invalid count bounds"),
    ("UPDATE fact_priority SET reporting_month=DATE '2025-12-01'; "
     "INSERT INTO dim_date VALUES (DATE '2025-12-01','2025-12','2025/26','Q4')",
     "latest month"),
])
def test_invalid_snapshot_does_not_replace_existing_export(
    bi_warehouse, tmp_path, mutation, message
):
    output = tmp_path / "export"
    export_bi(bi_warehouse, output)
    previous = {p.name: p.read_bytes() for p in output.iterdir()}
    with duckdb.connect(str(bi_warehouse)) as db:
        db.execute(mutation)
    with pytest.raises(ValueError, match=message):
        export_bi(bi_warehouse, output)
    assert {p.name: p.read_bytes() for p in output.iterdir()} == previous


def test_all_missing_pairs_returns_null_rate(bi_warehouse, tmp_path):
    with duckdb.connect(str(bi_warehouse)) as db:
        db.execute("UPDATE fact_rtt SET within_18_weeks=NULL")
    controls = export_bi(bi_warehouse, tmp_path / "export")["controls"]
    assert controls["latest_pct_within_18_complete_pairs"] is None
    assert controls["latest_rows_with_missing_18week_counts"] == 3


def test_missing_warehouse_fails_before_creating_export(tmp_path):
    output = tmp_path / "export"
    with pytest.raises(FileNotFoundError):
        export_bi(tmp_path / "absent.duckdb", output)
    assert not output.exists()
