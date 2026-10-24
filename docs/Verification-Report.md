# Verification report - 24 October 2026

## Executed
- Restored the original committed reference snapshot and materialised the analytical warehouse. This is not a fresh download from NHS England.
- Backend regression: 208 passed, 1 skipped, zero failures/errors, 209 collected. The skipped case requires a missing warehouse and is checked separately in degraded-pytest.xml.
- BI export: 10 acceptance tests pass; actual reference export produced six CSV tables and manifest.
- Warehouse integrity: every recorded technical check passed; 72,956 fact rows, 155 providers, 23 specialties, 21 months through June 2026; all 63 source audit rows show processed. See qa/results/warehouse-evidence.json.
- AWS extension: 17 local tests pass. The actual official reference warehouse also passes the strict release gate. These tests do not contact AWS.
- Power Query date/boolean parsing checked against exported representations; assets are not Desktop-executed. Postman collection JSON and all script syntax checked, not run in Postman.

## Important limits
The original source artifacts were built 19 August 2026 and end June 2026. Current NHS publication completeness and source correctness are not independently rechecked. Recorded forecasting metrics use model-selection folds; they do not establish independent held-out or 3/6-month predictive accuracy. A naive-drift candidate is different from the no-change evaluation comparator.

Docker build, AWS stack validation/deployment, regional live cost measurement, IAM runtime checks, notification delivery, recovery drills, browser accessibility, cross-browser checks, and native Power BI/Excel execution remain pending. The repository contains a Power BI import kit, not a PBIX. No NHS deployment, patient-data processing, clinical efficacy or real service improvement is claimed.

Machine-readable results: qa/results/verification-summary.json, pytest.xml, degraded-pytest.xml and warehouse-evidence.json. Runtime Python 3.12.14 on Windows; backend dependencies use the repository-pinned versions. Original infrastructure container targets Python 3.11 and has not been built here.
