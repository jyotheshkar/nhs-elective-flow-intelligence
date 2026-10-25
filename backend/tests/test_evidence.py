"""Independent evidence checks use a disposable DuckDB and deliberately corrupt it."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_evidence.py"
spec = importlib.util.spec_from_file_location("verify_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


@pytest.fixture
def evidence_db():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE fact_rtt(provider_code VARCHAR,specialty_code VARCHAR,reporting_month DATE,total_incomplete_pathways DOUBLE,within_18_weeks DOUBLE,over_52_weeks DOUBLE,data_source_type VARCHAR)")
    con.execute("INSERT INTO fact_rtt VALUES ('P1','C_100','2026-01-01',100,90,1,'DEMO_SYNTHETIC'),('P2','C_100','2026-01-01',900,450,90,'DEMO_SYNTHETIC'),('P1','C_100','2025-12-01',5000,5000,0,'DEMO_SYNTHETIC')")
    con.execute("CREATE TABLE dim_provider AS SELECT DISTINCT provider_code FROM fact_rtt")
    con.execute("CREATE TABLE dim_specialty AS SELECT DISTINCT specialty_code FROM fact_rtt")
    con.execute("CREATE TABLE dim_date AS SELECT DISTINCT reporting_month FROM fact_rtt")
    con.execute("CREATE TABLE warehouse_metadata AS SELECT COUNT(*) AS fact_rows FROM fact_rtt")
    con.execute("CREATE TABLE fact_priority(priority_score DOUBLE)")
    con.execute("INSERT INTO fact_priority VALUES (25),(75)")
    con.execute("CREATE TABLE fact_forecast(forecast_status VARCHAR,forecast_model VARCHAR,backtest_mape DOUBLE,backtest_skill_vs_naive DOUBLE)")
    con.execute("INSERT INTO fact_forecast VALUES ('ok','linear',4,0.2),('ok','naive',2,0),('insufficient_history',NULL,NULL,NULL)")
    con.execute("CREATE TABLE ingestion_audit(processing_status VARCHAR)")
    con.execute("INSERT INTO ingestion_audit VALUES ('processed')")
    for name in ('fact_rtt_metrics','fact_quality_issues','dim_provider_quality'):
        con.execute(f"CREATE TABLE {name}(id INTEGER)")
    yield con
    con.close()


def check(report, name):
    return next(item for item in report['checks'] if item['id']==name)


def test_latest_month_uses_weighted_counts_and_excludes_history(evidence_db):
    report = evidence.inspect_warehouse(evidence_db, 'DEMO_SYNTHETIC')
    assert report['passed']
    assert report['latest_month_kpis']['waiting_pathways']==1000
    assert report['latest_month_kpis']['weighted_within_18_pct']==54
    # An unweighted average would be 70%; the older month must not contaminate it.
    assert report['forecast_backtest_summary']['pct_beating_no_change']==50
    assert report['coverage']['reporting_months']==2


def test_duplicate_grain_and_metadata_drift_fail(evidence_db):
    evidence_db.execute("INSERT INTO fact_rtt SELECT * FROM fact_rtt LIMIT 1")
    report = evidence.inspect_warehouse(evidence_db)
    assert not report['passed']
    assert not check(report,'grain_unique')['passed']
    assert not check(report,'metadata_fact_count')['passed']


def test_orphan_dimension_and_invalid_counts_fail(evidence_db):
    evidence_db.execute("UPDATE fact_rtt SET provider_code='ORPHAN',within_18_weeks=1000 WHERE provider_code='P2'")
    report = evidence.inspect_warehouse(evidence_db)
    assert not check(report,'provider_integrity')['passed']
    assert not check(report,'valid_counts')['passed']


def test_demo_cannot_pass_as_official(evidence_db):
    report = evidence.inspect_warehouse(evidence_db,'OFFICIAL_NHS_PUBLIC')
    assert not report['passed']
    assert check(report,'expected_source')['violations']==3


def test_missing_tables_returns_failure_without_partial_success(evidence_db):
    evidence_db.execute('DROP TABLE fact_forecast')
    report = evidence.inspect_warehouse(evidence_db)
    assert not report['passed']
    assert 'fact_forecast' in check(report,'required_tables')['detail']
