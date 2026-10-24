"""Tiny real DuckDB fixtures exercise data-release failure boundaries offline."""
from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
try:
    import duckdb
    import pandas
except ImportError:
    duckdb=None
spec=importlib.util.spec_from_file_location('aws_runtime_gate',ROOT/'infra/aws/runtime.py')
runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
TEMP=ROOT/'infra/aws/.test-tmp'
TEMP.mkdir(exist_ok=True)

@unittest.skipIf(duckdb is None,'DuckDB and pandas dependencies required')
class GateIntegration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEMP)
        self.path=Path(self.temp.name)
        con=duckdb.connect(str(self.path/'warehouse.duckdb'))
        con.execute("CREATE TABLE warehouse_metadata AS SELECT 'OFFICIAL_NHS_PUBLIC' AS data_source_type, 2 AS fact_rows, 2 AS reporting_months")
        con.execute("CREATE TABLE fact_rtt (provider_code VARCHAR, specialty_code VARCHAR, reporting_month DATE, total_incomplete_pathways DOUBLE, completed_pathways DOUBLE)")
        con.execute("INSERT INTO fact_rtt VALUES ('A','X','2026-05-01',100,20),('A','X','2026-06-01',110,20)")
        con.execute('CREATE TABLE ingestion_audit (dataset VARCHAR, reporting_period VARCHAR, processing_status VARCHAR)')
        for dataset in ['incomplete','admitted','non_admitted']:
            for month in ['2026-05','2026-06']:
                con.execute("INSERT INTO ingestion_audit VALUES (?,?, 'processed')",[dataset,month])
        for table in runtime.REQUIRED_TABLES-{'warehouse_metadata','fact_rtt','ingestion_audit'}:
            con.execute('CREATE TABLE '+table+' (dummy INTEGER)')
        con.close()
    def tearDown(self): self.temp.cleanup()
    def mutate(self, sql):
        con=duckdb.connect(str(self.path/'warehouse.duckdb'))
        try: con.execute(sql)
        finally: con.close()
    def test_complete_candidate_passes(self):
        self.assertEqual(runtime.inspect_warehouse(self.path,2)['fact_rows'],2)
    def test_missing_source_month_refused(self):
        self.mutate("DELETE FROM ingestion_audit WHERE dataset='admitted' AND reporting_period='2026-06'")
        with self.assertRaisesRegex(ValueError,'Missing source workbook'):runtime.inspect_warehouse(self.path,2)
    def test_failed_source_refused(self):
        self.mutate("UPDATE ingestion_audit SET processing_status='parse_failed' WHERE dataset='admitted'")
        with self.assertRaisesRegex(ValueError,'failed ingestion audit'):runtime.inspect_warehouse(self.path,2)
    def test_duplicate_grain_refused(self):
        self.mutate('INSERT INTO fact_rtt SELECT * FROM fact_rtt LIMIT 1')
        with self.assertRaisesRegex(ValueError,'Duplicate canonical grain'):runtime.inspect_warehouse(self.path,2)
    def test_negative_pathways_refused(self):
        self.mutate('UPDATE fact_rtt SET completed_pathways=-1')
        with self.assertRaisesRegex(ValueError,'Negative pathways'):runtime.inspect_warehouse(self.path,2)
    def test_reporting_gap_refused(self):
        self.mutate("UPDATE fact_rtt SET reporting_month='2026-08-01' WHERE reporting_month='2026-06-01'")
        with self.assertRaisesRegex(ValueError,'Gap in reporting'):runtime.inspect_warehouse(self.path,2)
    def test_metadata_row_mismatch_refused(self):
        self.mutate('UPDATE warehouse_metadata SET fact_rows=3')
        with self.assertRaisesRegex(ValueError,'Metadata row-count'):runtime.inspect_warehouse(self.path,2)
    def test_synthetic_candidate_refused(self):
        self.mutate("UPDATE warehouse_metadata SET data_source_type='DEMO_SYNTHETIC'")
        with self.assertRaisesRegex(ValueError,'No official data'):runtime.inspect_warehouse(self.path,2)
    def test_required_table_missing_refused(self):
        self.mutate('DROP TABLE fact_forecast')
        with self.assertRaisesRegex(ValueError,'Missing warehouse tables'):runtime.inspect_warehouse(self.path,2)

if __name__=='__main__':unittest.main(verbosity=2)
