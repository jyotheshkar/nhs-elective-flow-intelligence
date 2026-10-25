# AWS extension verification - 24 October 2026

## Completed locally

- `python infra/aws/test_runtime.py`: 8/8 passed. Exercises exact-file manifests, download integrity, tampered bytes, invalid paths, synthetic marker, missing/duplicate objects and safe CloudFormation defaults/references.
- `python infra/aws/test_gate_integration.py`: 9/9 passed with real tiny DuckDB fixtures. Exercises complete candidate, failed/missing source workbook, duplicate grain, negative pathway counts, period gap, missing warehouse table, metadata row mismatch and synthetic candidate rejection.
- `python -m compileall -q infra/aws`: passed.
- CloudFormation JSON parsed and internal Ref/GetAtt targets checked. This is not AWS schema/service validation.
- SVG and Draw.io XML parsed. Rendered Architecture.png visually reviewed for legibility and connections.
- Ran `inspect_warehouse(Path('data/processed'),21)` against the materialised committed official-data snapshot: PASSED without changing the gate. Found 72,956 fact rows, 155 providers, 23 specialties, 21 monthly periods, latest reporting period June 2026. All three source-workbook families were present for those months and audit statuses were processed.

The official snapshot metadata carries build timestamp 19 August 2026. This verification did not download current NHS publications or rerun the original source ingestion. It validates the restored snapshot, not current national waiting-list figures. The metadata's model-accuracy and quality scores are not independently recomputed by this AWS gate.

## Still pending

Docker build, dependency/image security review in the target account, CloudFormation service validation, live Fargate ingestion, IAM evaluation, S3 conditional writes, SNS email confirmation and delivery, App Runner readiness/CORS, representative latency/load measurements, data-promotion and rollback drills, and actual London billing.

No AWS deployment was performed. CV/application wording must distinguish implemented and locally tested release controls from cloud-operating experience.
