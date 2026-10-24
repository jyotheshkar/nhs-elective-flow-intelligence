# Power BI and Excel Evidence Kit

Status: an import-ready kit, not a completed or Desktop-validated PBIX report.
The existing Next.js dashboard remains the running demonstration. This kit makes
its aggregate analytical model reproducible in Power BI without pretending the
author has completed an assessed Power BI qualification.

## Produce a traceable export

From the repository root, with backend dependencies installed:

```powershell
python scripts/build_warehouse.py --demo
python scripts/export_bi.py --warehouse data/warehouse.duckdb --output bi/export
```

Use the warehouse path printed by the build if configured differently. To export
official data, build or materialise the official warehouse first. Never label a
demo export as NHS statistics. Check `manifest.json`: source type, latest month,
fact count, weighted numerator/denominator, missing-count coverage and file hashes.
Do not copy updated files into a report while a refresh is running.

The exporter checks exact grain, nonnull relationship keys, dimension uniqueness,
referential integrity, month-start dates, exclusion of the C_999 aggregate, one
recognised source type and build-manifest reconciliation. Invalid input stops
before existing files change. Six CSV files are published followed by a manifest.
This is a local handoff, not a concurrent multi-reader transaction; for shared
refreshes publish a complete immutable release directory and switch readers only
after its manifest exists. No patient-identifiable data is handled.

## Assemble the report in Power BI Desktop

1. Create a blank report; disable automatic relationship detection for this file.
2. Create text parameter `ExportFolder`, containing the full export directory with
   its trailing slash. This directory must be accessible to the refresh identity.
3. Create Blank Query `ReadCsv`; paste `bi/Import.pq` into Advanced Editor.
4. Create six queries separately from `bi/Queries.pq`, preserving their exact
   names. Disable load for the helper function; enable load for the six tables.
5. Create the six one-to-many active relationships below, all single direction
   from dimension to fact. Leave BuildMetadata disconnected. Do not relate facts
   directly and do not use bidirectional relationships.
6. Sort DimDate[month_key] by DimDate[reporting_month]. DimDate has one row per
   reporting month: it is a monthly period dimension, not a contiguous daily
   calendar. Do not mark it as a daily date table or add DATEADD time intelligence.
7. Paste each measure from `bi/Measures.dax` individually. Hide numeric fact
   columns from report view so raw sums cannot replace explicit measures.
8. Import `bi/NHS-Elective-Theme.json`. Use readable text and accessible contrast.
   NHS blue is a design reference; this independent prototype is not NHS branded,
   affiliated or endorsed.
9. Add a single-select DimDate[month_key] slicer. Select the latest month. Add
   provider, region and specialty slicers from dimensions.
10. Refresh, reconcile the controls below, save your own PBIX and capture screens.
    Claim Power BI report delivery only after this step has actually been done.

| One-side key | Many-side key |
| --- | --- |
| DimProvider[provider_code] | FactRTT[provider_code] |
| DimSpecialty[specialty_code] | FactRTT[specialty_code] |
| DimDate[reporting_month] | FactRTT[reporting_month] |
| DimProvider[provider_code] | FactPriority[provider_code] |
| DimSpecialty[specialty_code] | FactPriority[specialty_code] |
| DimDate[reporting_month] | FactPriority[reporting_month] |

## Two useful report pages

**Operational Overview:** source label and reporting period at the top; Waiting
List, Within 18 Weeks %, Over 52 Weeks and Missing 18 Week Count Rows cards; a
waiting-list trend by month; provider/specialty table with priority score and raw
counts; single-month slicer. To show a full trend while the page is single-month,
turn off that slicer's interaction with the trend chart only. Other dimensional
slicers must still affect the trend. Priority is latest-month only; historical
selection correctly gives no priority scores.

**Data Assurance:** metadata build time and source type, count coverage, latest
month, and an explanation of the weighted calculation. Show a missing-data
warning when the missing-count row measure is positive. Never present complete-
pair percentages as if they cover every service.

A waiting list is a stock at a point in time. Adding all monthly stocks invents a
total. Stock measures therefore return blank unless exactly one month is in
context. Activity is a flow and may be added across reporting months, but missing
activity remains a coverage concern. Priority scores are not additive; display
only at provider-specialty-period level. Do not sum, average into a national
urgency score or interpret the operational index as clinical triage.

## Acceptance checks in Desktop (still required)

- All-provider latest waiting-list card equals manifest latest_waiting_list.
- The 18-week percentage equals the manifest complete-pair ratio, with matching
  missing-count coverage. Format the DAX fraction as a percentage.
- A 1,000-pathway service at 90% and a 100-pathway service at 10% combine to
  82.727%, not the average 50%. Missing numerator rows are excluded from both
  numerator and denominator and counted visibly.
- One provider or specialty slicer filters both facts through the dimensions.
- Clearing month selection returns blank snapshot cards and an explanatory label;
  every point on the trend has a single month and remains computable.
- Historical month selection gives blank priority rather than today's score.
- Demo source label remains visible in every capture/export. Source mode changes
  require rebuilding/exporting/refreshing all six tables together.
- Report is operable with keyboard and labels remain readable at 100% zoom.
- Document actual Desktop version, refresh timestamp, actual results and any
  defects before claiming these checks passed.

## Interview preparation

Explain why SUM(within_18)/SUM(total) needs identical row coverage; why waiting
lists are not summed over time; why dimensions filter facts but not each other;
why the monthly period table is not a daily date table; and why a changing
relative priority score does not by itself prove absolute deterioration.

Official syntax references checked 24 October 2026:
- https://learn.microsoft.com/en-us/powerquery-m/csv-document
- https://learn.microsoft.com/en-us/powerquery-m/table-transformcolumntypes
- https://learn.microsoft.com/en-us/dax/divide-function-dax
- https://learn.microsoft.com/en-us/dax/calculate-function-dax
- https://learn.microsoft.com/en-us/dax/removefilters-function-dax
