"""Immutable S3 releases for the public-statistics portfolio workload.

Build mode produces candidates only. An operator reviews and pins RELEASE_ID in
CloudFormation before the API uses it. No patient-level data is accepted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_TABLES = {
    'dim_provider', 'dim_specialty', 'dim_date', 'fact_rtt',
    'fact_rtt_metrics', 'fact_forecast', 'fact_priority',
    'fact_quality_issues', 'dim_provider_quality', 'ingestion_audit',
    'warehouse_metadata',
}

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def checked_release(value: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
        raise ValueError('Invalid release ID')
    return value

def validate_manifest(manifest: dict, release: str) -> list[dict]:
    if manifest.get('release_id') != checked_release(release):
        raise ValueError('Manifest release mismatch')
    if manifest.get('data_source_type') != 'OFFICIAL_NHS_PUBLIC':
        raise ValueError('Only official public aggregate data may be released')
    files = manifest.get('files', [])
    expected = {name + '.parquet' for name in REQUIRED_TABLES} | {'warehouse.duckdb'}
    names = [entry.get('name') for entry in files]
    if len(names) != len(set(names)) or set(names) != expected:
        raise ValueError('Manifest must contain exactly the expected warehouse files')
    for entry in files:
        if not re.fullmatch(r'[a-f0-9]{64}', entry.get('sha256', '')):
            raise ValueError('Invalid SHA-256')
        if not isinstance(entry.get('bytes'), int) or not 0 < entry['bytes'] <= 512 * 1024 * 1024:
            raise ValueError('Invalid object size')
    return files

def download_release(s3, bucket: str, release: str, destination: Path) -> dict:
    release = checked_release(release)
    prefix = 'releases/' + release + '/'
    raw = s3.get_object(Bucket=bucket, Key=prefix+'manifest.json')['Body'].read(1024 * 1024)
    manifest = json.loads(raw)
    entries = validate_manifest(manifest, release)
    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = destination / entry['name']
        s3.download_file(bucket, prefix+entry['name'], str(target))
        if target.stat().st_size != entry['bytes'] or sha256(target) != entry['sha256']:
            target.unlink(missing_ok=True)
            raise ValueError('Checksum/size verification failed: '+entry['name'])
    (destination/'release.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest

def inspect_warehouse(processed: Path, months: int) -> dict:
    import duckdb
    import pandas as pd
    con = duckdb.connect(str(processed/'warehouse.duckdb'), read_only=True)
    try:
        names = {row[0] for row in con.execute('SHOW TABLES').fetchall()}
        if not REQUIRED_TABLES <= names:
            raise ValueError('Missing warehouse tables')
        meta = con.execute('SELECT * FROM warehouse_metadata').df().iloc[0].to_dict()
        if meta['data_source_type'] != 'OFFICIAL_NHS_PUBLIC' or int(meta['fact_rows']) <= 0:
            raise ValueError('No official data')
        fact = con.execute('SELECT * FROM fact_rtt').df()
        if fact.duplicated(['provider_code','specialty_code','reporting_month']).any():
            raise ValueError('Duplicate canonical grain')
        if len(fact) != int(meta['fact_rows']):
            raise ValueError('Metadata row-count mismatch')
        if int(meta['reporting_months']) != months:
            raise ValueError('Unexpected number of reporting months')
        for col in ['total_incomplete_pathways', 'completed_pathways']:
            if fact[col].dropna().lt(0).any():
                raise ValueError('Negative pathways: '+col)
        audit = con.execute('SELECT * FROM ingestion_audit').df()
        if audit.empty or not audit['processing_status'].eq('processed').all():
            raise ValueError('Incomplete or failed ingestion audit')
        periods = set(pd.to_datetime(fact['reporting_month']).dt.strftime('%Y-%m'))
        if periods != set(pd.period_range(min(periods), max(periods), freq='M').astype(str)):
            raise ValueError('Gap in reporting-month sequence')
        for dataset in ['incomplete','admitted','non_admitted']:
            observed = set(pd.to_datetime(audit.loc[audit['dataset'].eq(dataset),'reporting_period']).dt.strftime('%Y-%m'))
            if not periods <= observed:
                raise ValueError('Missing source workbook for '+dataset)
        # Source/model findings remain visible: an unusual movement is not assumed to be an error.
        return json.loads(json.dumps(meta, default=str))
    finally:
        con.close()

def build(s3, bucket: str, months: int) -> dict:
    if not 6 <= months <= 36:
        raise ValueError('months must be 6..36')
    environment = dict(os.environ, APP_DATA_MODE='official')
    subprocess.run([sys.executable, str(ROOT/'scripts/build_warehouse.py'), '--months', str(months)],
                   check=True, cwd=ROOT, env=environment, timeout=3600)
    processed = Path(os.environ.get('PROCESSED_DIR', str(ROOT/'data/processed')))
    meta = inspect_warehouse(processed, months)
    floor = os.environ.get('MIN_REPORTING_MONTH', '')
    baseline = os.environ.get('BASELINE_RELEASE_ID', 'not-yet-published')
    if baseline != 'not-yet-published':
        prior = json.loads(s3.get_object(Bucket=bucket, Key='releases/'+checked_release(baseline)+'/manifest.json')['Body'].read())
        floor = max(floor, prior['metadata']['latest_reporting_month'])
    if not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])', str(meta['latest_reporting_month'])) or meta['latest_reporting_month'] < floor:
        raise ValueError('Reporting period regressed below approved baseline')
    release = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    files = []
    for name in sorted(REQUIRED_TABLES):
        path = processed/(name+'.parquet')
        files.append({'name':path.name,'bytes':path.stat().st_size,'sha256':sha256(path)})
    db = processed/'warehouse.duckdb'
    files.append({'name':db.name,'bytes':db.stat().st_size,'sha256':sha256(db)})
    manifest = {'schema_version':1,'release_id':release,'data_source_type':'OFFICIAL_NHS_PUBLIC',
                'created_at':datetime.now(timezone.utc).isoformat(),'metadata':meta,'files':files,
                'approval':'CANDIDATE_REQUIRES_OPERATOR_REVIEW'}
    validate_manifest(manifest, release)
    # Upload all bytes before the commit marker. A crash cannot publish a complete candidate manifest.
    for entry in files:
        path = processed/entry['name']
        with path.open('rb') as stream:
            s3.put_object(Bucket=bucket, Key='releases/'+release+'/'+path.name,
                          Body=stream, ServerSideEncryption='AES256', IfNoneMatch='*')
    raw = Path(os.environ.get('RAW_DIR', str(ROOT/'data/raw')))
    for path in raw.rglob('*.xlsx'):
        with path.open('rb') as stream:
            s3.put_object(Bucket=bucket, Key='raw/'+release+'/'+path.relative_to(raw).as_posix(),
                          Body=stream, ServerSideEncryption='AES256', IfNoneMatch='*')
    s3.put_object(Bucket=bucket, Key='releases/'+release+'/manifest.json',
                  Body=json.dumps(manifest).encode(), ContentType='application/json',
                  ServerSideEncryption='AES256', IfNoneMatch='*')
    return manifest

def serve(s3, bucket: str, release: str) -> None:
    processed = ROOT/'data/processed'/checked_release(release)
    download_release(s3, bucket, release, processed)
    os.environ['PROCESSED_DIR'] = str(processed)
    os.environ['APP_DATA_MODE'] = 'official'
    os.environ['PYTHONPATH'] = str(ROOT/'backend')
    # All checks finish before the listening socket opens; no health success with partial data.
    os.execv(sys.executable, [sys.executable, '-m', 'uvicorn', 'app.main:app',
                             '--host','0.0.0.0','--port',os.environ.get('PORT','8000')])

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['build','serve'])
    parser.add_argument('--months', type=int, default=18)
    args = parser.parse_args()
    import boto3
    s3 = boto3.client('s3')
    try:
        if args.mode == 'build':
            manifest = build(s3, os.environ['RELEASE_BUCKET'], args.months)
            print(json.dumps({'event':'refresh_complete','release_id':manifest['release_id'],
                              'latest_reporting_month':manifest['metadata']['latest_reporting_month']}), flush=True)
        else:
            serve(s3, os.environ['RELEASE_BUCKET'], os.environ['RELEASE_ID'])
    except Exception as exc:
        print(json.dumps({'event':'refresh_failed' if args.mode=='build' else 'startup_failed',
                          'error':str(exc)}), flush=True)
        raise

if __name__ == '__main__':
    main()
