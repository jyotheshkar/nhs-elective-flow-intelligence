# NHS Elective Flow - Quality Evidence

Independent portfolio work using aggregate public statistics or explicitly labelled synthetic data. These assets support a demonstration of software/data quality practice. They do not establish clinical safety approval, NHS deployment or patient benefit.

## Evidence status

- The Postman collection and manual charters are **authored, not executed** until an execution report is saved.
- `scripts/verify_evidence.py` produces measured warehouse facts and structural integrity results. A passing report is narrower than a full statistical validation or source-completeness audit.
- Existing `backend/tests/` cover analytics, scenarios, validation and API contracts. Only an actual pytest report establishes pass/skip counts.
- Run technical demonstrations using synthetic data first. For official data, set `expected_source=OFFICIAL_NHS_PUBLIC` and retain the warehouse checksum and reporting period.
- Do not write confidential Amazon examples, patient data, referee details or application information into this public project.

## Reproduce

From the repository root with backend requirements installed:

```powershell
python scripts/build_warehouse.py --demo
python scripts/verify_evidence.py --expected-source DEMO_SYNTHETIC
cd backend
python -m pytest --junitxml=../qa/results/pytest.xml
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Import `NHS-Elective-Regression.postman_collection.json` and `Local-Demo.postman_environment.json` into Postman. Select the local environment and run all 15 requests in order. The rankings request discovers a forecastable service; no real provider identifiers are hardcoded. A fixture with no forecastable/active service should fail this test, rather than quietly skipping scenario assertions.

Optional installed Newman CLI:

```powershell
newman run qa/NHS-Elective-Regression.postman_collection.json -e qa/Local-Demo.postman_environment.json --reporters cli,json --reporter-json-export qa/results/postman.json
```

For an official-data run, change the environment source marker and keep results separate from synthetic results. Do not describe demo-model accuracy as performance on NHS data.

## Risk-based test plan and traceability

Risk is the harm to interpretation or service availability from a software/data failure. This is not an assessment of patient clinical risk.

| Requirement | Failure risk | Priority | Evidence / check | Execution status |
|---|---|---|---|---|
| R01: Identify official versus synthetic data consistently | Recruiter/user mistakes synthetic figures for NHS evidence | High | Postman R02/R14; verifier expected_source; manual banner/export check | Script status recorded only when executed; manual pending |
| R02: One provider x specialty x month fact | Duplicate loads inflate backlog and rolling metrics | High | Verifier grain_unique; duplicate-corruption test | Recorded by test run |
| R03: Weighted 18-week percentage | Small specialties receive same weight as large services | High | Verifier latest-month sums; test with 100 and 900 pathways yields 54%, not 70% | Recorded by test run |
| R04: Latest snapshot excludes historic backlog totals | Months are summed as if concurrent patients | High | Verifier latest reporting_month predicate; independent fixture includes older 5,000-row value | Recorded by test run |
| R05: Scores decompose and remain bounded | Incorrect ranking presented as objective truth | High | Postman R03/R04; existing priority tests | Recorded by test run |
| R06: Forecast bounds and caveats travel with result | Indicative uncertainty presented as rigorous assurance | High | Postman R05; existing forecast tests; manual wording review | Manual review pending |
| R07: Zero uplift reproduces baseline; additional activity cannot increase backlog | Capacity story mathematically inconsistent | High | Postman R06/R07; existing scenario tests | Recorded by test run |
| R08: Reject invalid/malicious parameters | Invalid output or service disruption | High | Postman R08-R12/R15; existing API tests | Recorded by test run |
| R09: Unknown service gives clear failure | Missing result mistaken for zero burden | Medium | Postman R13; manual empty-state review | Manual pending |
| R10: Warehouse/source revisions safely published | Incomplete refresh replaces usable dataset | High | AWS release gates and last-known-good runbook; manually rehearse failed candidate promotion | Cloud rehearsal pending |
| R11: Users can understand, navigate and export results | Usability/accessibility excludes users or loses context | High | Exploratory charters below | **Not executed** |
| R12: Data relationships and metadata agree | Joins silently lose services or claims become stale | High | Verifier orphan checks, source marker, metadata fact count, required tables | Recorded by test run |

## Test levels and release decision

1. Unit/invariant checks: formula boundaries, missing input, score decomposition, forecasting fallback and noncausal scenario identities.
2. Integration: canonical warehouse joins, source labels, data release contents, API responses and export provenance.
3. System: end-to-end filter -> service -> scenario -> export interaction in a browser.
4. Non-functional: keyboard/accessibility, cross-browser behaviour, API latency under a stated local load, controlled failure recovery and deployment security review.

A release candidate needs no unexplained high-severity failures, explicit source mode, traceable input/version, reproducible automated results and documented remaining manual/cloud checks. Unknowns are recorded as unknowns. Unit success does not imply the browser, cloud deployment or all public-source workbooks were tested.

## Exploratory charters - NOT EXECUTED

### Accessibility and usability (45 minutes)

- Keyboard only: focus order, visible focus, controls, filter resets, modal dismissal and export download.
- Screen reader: headings, labels, status announcements, table headers, loading/empty/error messages; ensure charts have equivalent textual values.
- Contrast/colour: score severity understandable without colour; readable normal/hover/disabled states.
- Zoom 200% and narrow viewport: no inaccessible off-screen controls or clipped essential labels.
- Check whether chart tooltips hide units, source period or caveats; compare tooltips with table data.
- Test one recent stable Chromium browser and a second browser; retain versions and screenshots.

### Data interpretation (45 minutes)

- Compare a small and large specialty; distinguish relative priority from absolute clinical urgency.
- Identify stale reporting period and missing history; confirm null is not displayed as a real zero.
- Change provider/specialty filters; verify chart scope, KPI denominator, export rows and reporting period agree.
- Change activity uplift 0/5/10/20%; explain the accounting identity and omitted operational feasibility constraints.
- Inspect known revisions, source checksum and data mode; identify whether repeated refresh produces duplicates.

### Recovery (30 minutes, isolated environment only)

- Start without warehouse; confirm 503 guidance and UI remedy.
- Point the API at an incomplete candidate release; confirm failed startup/promotion does not replace the approved release.
- Simulate a failed download/build; retain logs and restore last-known-good release.
- No deliberate fault injection against the public demo or employer systems.

## Defects and evidence integrity

Use `Defect-Template.md` for a real reproducible defect. Do not invent a defect count or label a planned scenario as an incident that occurred. Repository comments describing older fixes are historical source claims, not new discoveries from this run.

When a check fails, retain the exact command, environment, source marker, timestamp, commit/hash, expected versus actual result and smallest reproduction. Describe what was tested and what remains untested at interview.
