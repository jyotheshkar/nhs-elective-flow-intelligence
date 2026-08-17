# Data dictionary

Canonical fields in the analytical warehouse.

**Source** values:
- `NHS England (published)` — read directly from a published workbook column
- `Derived` — computed by this application from published values
- `Reference` — from `config/sources.yaml` or a coded lookup

> Fields marked **Derived** are produced by this application and are **not** NHS England
> statistics. They must not be presented as such.

---

## `dim_provider`

One row per provider organisation. Attributes reflect the most recent reporting month.

| Field | Type | Nullable | Definition | Source | Transformation |
|---|---|---|---|---|---|
| `provider_code` | string | No | NHS provider organisation code (e.g. `R1H`) | NHS England (published) | Trimmed, upper-cased |
| `provider_name` | string | No | Provider organisation name | NHS England (published) | Title-cased; NHS acronyms preserved; apostrophes and conjunctions handled |
| `provider_short_name` | string | Yes | Compact label for dense tables and axis ticks | Derived | `provider_name` with "NHS Trust"/"NHS Foundation Trust" removed |
| `region_code` | string | Yes | NHS England region code (e.g. `Y56`) | NHS England (published) | Trimmed, upper-cased |
| `region_name` | string | Yes | Region display name | Reference | Mapped from `region_code`; falls back to the code if unmapped |
| `provider_type` | string | No | `NHS Foundation Trust` / `NHS Trust` / `Other provider` | Derived | Classified from the published name — NHS England does not publish a type column in these files |

---

## `dim_specialty`

One row per treatment function.

| Field | Type | Nullable | Definition | Source | Transformation |
|---|---|---|---|---|---|
| `specialty_code` | string | No | Treatment function code (e.g. `C_110`, `X05`) | NHS England (published) | Trimmed, upper-cased. `C_999` (Total) excluded |
| `specialty_name` | string | No | Treatment function name | NHS England (published) | Whitespace normalised |
| `specialty_short_name` | string | Yes | Name without the trailing "Service" | Derived | Suffix removed |
| `specialty_group` | string | No | `Surgical` / `Medical` / `Mental Health` / `Paediatrics` / `Other` | Derived | Coded grouping used for peer benchmarking |

---

## `dim_date`

One row per reporting month.

| Field | Type | Nullable | Definition | Source | Transformation |
|---|---|---|---|---|---|
| `reporting_month` | date | No | First day of the reporting month | NHS England (published) | Parsed from the `MonYY` fragment in the filename |
| `month_key` | string | No | `YYYY-MM` | Derived | Formatted |
| `month_label` | string | No | e.g. `Mar 2026` | Derived | Formatted |
| `year` | int | No | Calendar year | Derived | |
| `month_number` | int | No | 1–12 | Derived | |
| `quarter` | string | No | `Q1`–`Q4` (calendar) | Derived | |
| `financial_year` | string | No | NHS financial year, e.g. `2025/26` | Derived | April–March |
| `financial_quarter` | string | No | `Q1`–`Q4` (financial, April start) | Derived | |
| `month_index` | int | No | 0-based position in the loaded window | Derived | |
| `is_latest` | bool | No | True for the most recent loaded month | Derived | |

---

## `fact_rtt`

**Grain: one row per `provider_code` × `specialty_code` × `reporting_month`.**

| Field | Type | Nullable | Definition | Source | Transformation |
|---|---|---|---|---|---|
| `provider_code` | string | No | FK → `dim_provider` | NHS England (published) | |
| `specialty_code` | string | No | FK → `dim_specialty` | NHS England (published) | |
| `reporting_month` | date | No | FK → `dim_date` | NHS England (published) | |
| `month_key` | string | No | `YYYY-MM` | Derived | |
| `total_incomplete_pathways` | float | Yes | Patients waiting to start consultant-led treatment (the waiting list) | NHS England (published) | "Total number of incomplete pathways" |
| `within_18_weeks` | float | Yes | Incomplete pathways waiting < 18 weeks | NHS England (published) | "Total within 18 weeks" |
| `over_18_weeks` | float | Yes | Incomplete pathways waiting ≥ 18 weeks | Derived | `total − within_18`, floored at 0 |
| `over_52_weeks` | float | Yes | Waiting > 52 weeks | NHS England (published) | "Total 52 plus weeks" |
| `over_65_weeks` | float | Yes | Waiting > 65 weeks | NHS England (published) | "Total 65 plus weeks" |
| `over_78_weeks` | float | Yes | Waiting > 78 weeks | NHS England (published) | "Total 78 plus weeks" |
| `over_104_weeks` | float | Yes | Waiting > 104 weeks | NHS England (published) | From the `104 plus` weekly band |
| `pct_within_18_weeks` | float | Yes | % of the list within 18 weeks | Derived | `within_18 / total × 100`, safe-divide |
| `pct_over_18_weeks` | float | Yes | % of the list beyond 18 weeks | Derived | `over_18 / total × 100` |
| `pct_over_52_weeks` | float | Yes | % beyond 52 weeks | Derived | `over_52 / total × 100` |
| `pct_over_65_weeks` | float | Yes | % beyond 65 weeks | Derived | `over_65 / total × 100` |
| `pct_over_78_weeks` | float | Yes | % beyond 78 weeks | Derived | `over_78 / total × 100` |
| `pct_over_104_weeks` | float | Yes | % beyond 104 weeks | Derived | `over_104 / total × 100` |
| `median_wait_weeks` | float | Yes | Median wait of those still waiting | NHS England (published) | "Average (median) waiting time (in weeks)" |
| `percentile_92_wait_weeks` | float | Yes | 92nd percentile wait | NHS England (published) | "92nd percentile waiting time (in weeks)" |
| `admitted_activity` | float | Yes | Completed admitted pathways in the month | NHS England (published) | Admitted workbook, "Total number of completed pathways (all)" |
| `non_admitted_activity` | float | Yes | Completed non-admitted pathways in the month | NHS England (published) | NonAdmitted workbook, same column |
| `completed_pathways` | float | Yes | Total completed activity | Derived | `admitted + non_admitted`, `min_count=1` so both-null stays null |
| `pct_within_18_weeks_source` | float | Yes | Publication's own % within 18 weeks | NHS England (published) | Rescaled from fraction to percentage; retained for reconciliation |
| `pct_over_52_weeks_source` | float | Yes | Publication's own % over 52 weeks | NHS England (published) | As above |
| `data_source_type` | string | No | `OFFICIAL_NHS_PUBLIC` or `DEMO_SYNTHETIC` | Derived | Set at ingestion |

**Nullability note.** Suppressed (`*`) and unavailable (`-`) published values become
null, never zero.

---

## `fact_rtt_metrics`

`fact_rtt` plus derived longitudinal metrics. Same grain. All computed **within** a
provider × specialty series ordered by month.

| Field | Type | Nullable | Definition | Source | Transformation |
|---|---|---|---|---|---|
| `waiting_list_prev_month` | float | Yes | Previous month's list | Derived | `shift(1)` |
| `backlog_change_1m` | float | Yes | Month-on-month change (pathways) | Derived | `L_t − L_{t−1}` |
| `backlog_change_3m` / `_6m` | float | Yes | Change over 3 / 6 months | Derived | `L_t − L_{t−k}` |
| `backlog_growth_1m_pct` | float | Yes | Month-on-month growth % | Derived | Safe-divide |
| `backlog_growth_3m_pct` | float | Yes | 3-month growth % | Derived | `(L_t − L_{t−3}) / L_{t−3} × 100` |
| `backlog_growth_6m_pct` | float | Yes | 6-month growth % | Derived | As above, k=6 |
| `waiting_list_rolling_3m` / `_6m` | float | Yes | Rolling mean list size | Derived | min_periods 2 / 3 |
| `trend_slope_3m` / `_6m` | float | Yes | OLS slope, pathways per month | Derived | Rolling window regression |
| `trend_slope_6m_pct_of_list` | float | Yes | 6-month slope as % of current list | Derived | Size-normalised for cross-service comparison |
| `backlog_change_volatility_6m` | float | Yes | SD of monthly changes | Derived | Rolling sd, min_periods 3 |
| `pct_within_18_weeks_prev` | float | Yes | Previous month's 18-week % | Derived | `shift(1)` |
| `pct_within_18_weeks_change_1m` | float | Yes | MoM change, **percentage points** | Derived | Difference |
| `pct_within_18_weeks_change_3m` | float | Yes | 3-month change, percentage points | Derived | Difference |
| `months_backlog_rising` | float | Yes | Consecutive months the list has grown | Derived | Run resets on a fall or a data gap |
| `months_performance_falling` | float | Yes | Consecutive months 18-week % has fallen | Derived | As above |
| `share_months_rising_6m` | float | Yes | % of the last 6 months in which the list grew | Derived | Rolling mean of an indicator × 100 |
| `activity_prev_month` | float | Yes | Previous month's completed activity | Derived | `shift(1)` |
| `activity_change_1m_pct` / `_3m_pct` | float | Yes | Activity growth % | Derived | Safe-divide |
| `rolling_activity_3m` | float | Yes | Mean monthly completed activity, 3 months | Derived | min_periods 2 |
| `months_to_clear_at_current_activity` | float | Yes | Months to clear the list at recent activity | Derived | `L_t / rolling_activity_3m` |
| `implied_additions` | float | Yes | **Implied** additions to the list | Derived | `backlog_change_1m + completed_pathways`. An accounting identity — **not** observed referrals |
| `rolling_implied_additions_3m` | float | Yes | 3-month mean of the above | Derived | |
| `activity_gap_pct` | float | Yes | Backlog growth minus activity growth | Derived | Positive = backlog outpacing activity |

---

## `fact_forecast`

One row per provider × specialty series.

| Field | Type | Nullable | Definition | Source |
|---|---|---|---|---|
| `forecast_status` | string | No | `ok` or `insufficient_history` | Derived |
| `forecast_model` | string | Yes | Selected model | Derived |
| `forecast_history_months` | int | No | Usable observations | Derived |
| `forecast_confidence` | string | No | `High` / `Moderate` / `Low` / `Insufficient data` | Derived |
| `forecast_message` | string | Yes | Explanation when no forecast is produced | Derived |
| `forecast_last_actual` | float | Yes | Most recent observed list size | Derived |
| `forecast_1m` / `_3m` / `_6m` | float | Yes | Point forecast at horizon | Derived |
| `forecast_{h}m_lower` / `_upper` | float | Yes | Indicative 80% interval bounds | Derived |
| `forecast_{h}m_month` | string | Yes | `YYYY-MM` of the forecast horizon | Derived |
| `forecast_change_3m_pct` / `_6m_pct` | float | Yes | Modelled % change vs last actual | Derived |
| `backtest_mae` / `_rmse` / `_mape` | float | Yes | Out-of-sample error | Derived |
| `backtest_folds` | int | Yes | Number of backtest folds | Derived |
| `backtest_naive_mae` | float | Yes | Naive benchmark MAE | Derived |
| `backtest_skill_vs_naive` | float | Yes | `1 − model_MAE / naive_MAE`; > 0 beats naive | Derived |

---

## `fact_priority`

Latest reporting month only, scored. Includes all `fact_rtt_metrics` and
`fact_forecast` fields, plus:

| Field | Type | Nullable | Definition | Source |
|---|---|---|---|---|
| `priority_score` | float | No | Operational priority index, 0–100 | Derived |
| `priority_band` | string | No | `LOW` / `MODERATE` / `HIGH` / `CRITICAL` | Derived |
| `priority_rank` | float | Yes | Rank among rankable services | Derived |
| `is_rankable` | bool | No | Waiting list ≥ 200 pathways | Derived |
| `score_backlog_pressure` | float | No | Component score, 0–100 | Derived |
| `score_long_wait_burden` | float | No | Component score, 0–100 | Derived |
| `score_performance_gap` | float | No | Component score, 0–100 | Derived |
| `score_forecast_risk` | float | No | Component score, 0–100 (50 when unavailable) | Derived |
| `score_persistence` | float | No | Component score, 0–100 | Derived |
| `contribution_{component}` | float | No | Weighted contribution; the five sum to `priority_score` | Derived |
| `max_contribution_{component}` | float | No | Component weight (30/25/20/15/10) | Derived |
| `peer_median_{measure}` | float | Yes | Specialty peer median | Derived |
| `national_median_{measure}` | float | Yes | Median across all loaded services | Derived |

---

## `fact_quality_issues`

One row per data quality finding.

| Field | Type | Nullable | Definition |
|---|---|---|---|
| `provider_code` | string | Yes | Null for warehouse-level findings |
| `provider_name` | string | Yes | Display name |
| `specialty_code` | string | Yes | Null for provider- or warehouse-level findings |
| `specialty_name` | string | Yes | Display name |
| `month` | string | Yes | `YYYY-MM`, null for cross-period findings |
| `issue_type` | string | No | `Unusual month-on-month change`, `Missing reporting months`, `Duplicate record`, `Negative count`, `Component exceeds total`, `Percentage out of range`, `Derivation mismatch`, `Stale data` |
| `severity` | string | No | `High` / `Medium` / `Low` |
| `description` | string | No | Human-readable explanation |
| `observed_value` | float | Yes | The value that triggered the finding |
| `expected_value` | float | Yes | Reference or prior value |

---

## `ingestion_audit`

Provenance, one row per source file.

| Field | Type | Definition |
|---|---|---|
| `dataset` | string | `incomplete` / `admitted` / `non_admitted` / `demo` |
| `reporting_period` | string | `YYYY-MM` |
| `source_url` | string | Exact URL downloaded |
| `source_file` | string | Published filename |
| `source_page` | string | Publication page it was discovered on |
| `downloaded_at` | string | ISO 8601 UTC |
| `bytes_downloaded` | int | File size |
| `checksum_sha256` | string | SHA-256 of the downloaded file |
| `row_count` | int | Rows after cleaning |
| `processing_status` | string | `processed` / `download_failed` / `parse_failed` / `validation_failed` |
| `data_source_type` | string | `OFFICIAL_NHS_PUBLIC` / `DEMO_SYNTHETIC` |
| `published_date` | string | Publication date from the workbook metadata |
| `source_period_label` | string | Period label from the workbook metadata |
| `revision` | int | 0 = original, higher = later restatement |
| `message` | string | Error or warning detail |
| `ingested_at` | string | ISO 8601 UTC |

---

## `warehouse_metadata`

Single-row build manifest: `app_version`, `built_at`, `data_source_type`, `data_mode`,
`latest_reporting_month`, `reporting_months`, `provider_count`, `specialty_count`,
`fact_rows`, `quality_score`, `forecast_series_ok`, `forecast_series_insufficient`,
`forecast_median_mape`, `forecast_share_beating_naive`,
`referral_to_treatment_benchmark`, `min_waiting_list_for_ranking`, `build_messages`.

---

## Reference: NHS England region codes

| Code | Region |
|---|---|
| `Y56` | London |
| `Y58` | South West |
| `Y59` | South East |
| `Y60` | Midlands |
| `Y61` | East of England |
| `Y62` | North West |
| `Y63` | North East and Yorkshire |

## Reference: treatment function codes in the loaded data

| Code | Treatment function | Group |
|---|---|---|
| `C_100` | General Surgery Service | Surgical |
| `C_101` | Urology Service | Surgical |
| `C_110` | Trauma and Orthopaedic Service | Surgical |
| `C_120` | Ear Nose and Throat Service | Surgical |
| `C_130` | Ophthalmology Service | Surgical |
| `C_140` | Oral Surgery Service | Surgical |
| `C_150` | Neurosurgical Service | Surgical |
| `C_160` | Plastic Surgery Service | Surgical |
| `C_170` | Cardiothoracic Surgery Service | Surgical |
| `C_300` | General Internal Medicine Service | Medical |
| `C_301` | Gastroenterology Service | Medical |
| `C_320` | Cardiology Service | Medical |
| `C_330` | Dermatology Service | Medical |
| `C_340` | Respiratory Medicine Service | Medical |
| `C_400` | Neurology Service | Medical |
| `C_410` | Rheumatology Service | Medical |
| `C_430` | Elderly Medicine Service | Medical |
| `C_502` | Gynaecology Service | Surgical |
| `X02` | Other – Medical Services | Medical |
| `X03` | Other – Mental Health Services | Mental Health |
| `X04` | Other – Paediatric Services | Paediatrics |
| `X05` | Other – Surgical Services | Surgical |
| `X06` | Other – Other Services | Other |
| `C_999` | Total | **Excluded** (aggregate) |
