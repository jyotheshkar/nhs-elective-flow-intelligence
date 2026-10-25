"""Offline contract tests: no AWS credentials or API calls."""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMP = ROOT/'infra/aws/.test-tmp'
TEMP.mkdir(exist_ok=True)
spec = importlib.util.spec_from_file_location('aws_runtime', ROOT/'infra/aws/runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

class FakeS3:
    def __init__(self, manifest, contents):
        self.manifest, self.contents = manifest, contents
    def get_object(self, **kwargs):
        return {'Body':io.BytesIO(json.dumps(self.manifest).encode())}
    def download_file(self, bucket, key, target):
        Path(target).write_bytes(self.contents[key.split('/')[-1]])

def fixture():
    contents = {name+'.parquet':b'public-test' for name in runtime.REQUIRED_TABLES}
    contents['warehouse.duckdb'] = b'public-test'
    manifest = {'release_id':'test-123','data_source_type':'OFFICIAL_NHS_PUBLIC',
                'files':[{'name':name,'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()}
                         for name,value in contents.items()]}
    return manifest, contents

class ReleaseContracts(unittest.TestCase):
    def test_complete_download(self):
        manifest, contents = fixture()
        with tempfile.TemporaryDirectory(dir=TEMP) as td:
            runtime.download_release(FakeS3(manifest,contents),'bucket','test-123',Path(td))
            self.assertEqual(len(list(Path(td).glob('*.parquet'))),11)
    def test_tamper_fails_before_server_start(self):
        manifest, contents = fixture()
        contents['warehouse.duckdb']=b'tampered'
        with tempfile.TemporaryDirectory(dir=TEMP) as td:
            with self.assertRaisesRegex(ValueError,'Checksum'):
                runtime.download_release(FakeS3(manifest,contents),'bucket','test-123',Path(td))
    def test_synthetic_data_refused(self):
        manifest,_=fixture(); manifest['data_source_type']='DEMO_SYNTHETIC'
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'test-123')
    def test_path_traversal_refused(self):
        manifest,_=fixture(); manifest['files'][0]['name']='../../secret'
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'test-123')
        with self.assertRaises(ValueError): runtime.checked_release('../test')
    def test_missing_and_duplicate_files_refused(self):
        manifest,_=fixture(); manifest['files'].pop()
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'test-123')
        manifest,_=fixture(); manifest['files'].append(manifest['files'][0])
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'test-123')
    def test_wrong_release_refused(self):
        manifest,_=fixture()
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'other')
    def test_invalid_checksum_and_size_refused(self):
        manifest,_=fixture(); manifest['files'][0]['sha256']='invalid'
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'test-123')
        manifest,_=fixture(); manifest['files'][0]['bytes']=0
        with self.assertRaises(ValueError): runtime.validate_manifest(manifest,'test-123')
    def test_template_refs_and_safe_defaults(self):
        template=json.loads((ROOT/'infra/aws/template.json').read_text())
        known=set(template['Resources'])|set(template['Parameters'])|{'AWS::Region','AWS::StackName','AWS::AccountId','AWS::Partition'}
        def walk(value):
            if isinstance(value,dict):
                if 'Ref' in value:self.assertIn(value['Ref'],known)
                if 'Fn::GetAtt' in value:self.assertIn(value['Fn::GetAtt'][0],template['Resources'])
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        walk(template)
        self.assertEqual(template['Parameters']['DeployApi']['Default'],'false')
        self.assertEqual(template['Parameters']['ScheduleState']['Default'],'DISABLED')
        self.assertEqual(template['Resources']['DataBucket']['DeletionPolicy'],'Retain')
        statements=template['Resources']['ApiRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        self.assertEqual(statements[0]['Action'],'s3:GetObject')

if __name__=='__main__': unittest.main(verbosity=2)
