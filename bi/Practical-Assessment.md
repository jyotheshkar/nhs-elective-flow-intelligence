# SQL and Excel Practical Assessment

These exercises use public aggregate or labelled demo data. Complete them yourself
and explain your work aloud. They are preparation tasks, not claimed employment
achievements.

## 30-minute SQL task

Find each provider's latest waiting list, long-wait burden, 18-week percentage and
count of services with missing numerator/denominator. Rank by long-wait burden,
then explain which provider warrants investigation. Do not claim the rank
determines clinical urgency.

Reference solution for DuckDB:

```sql
WITH latest AS (
  SELECT MAX(reporting_month) AS period FROM fact_rtt
)
SELECT f.provider_code,
       SUM(f.total_incomplete_pathways) AS waiting_list,
       SUM(f.over_52_weeks) AS over_52_weeks,
       100.0 * SUM(CASE WHEN f.within_18_weeks IS NOT NULL
                         AND f.total_incomplete_pathways > 0
                        THEN f.within_18_weeks END)
         / NULLIF(SUM(CASE WHEN f.within_18_weeks IS NOT NULL
                           AND f.total_incomplete_pathways > 0
                          THEN f.total_incomplete_pathways END), 0)
           AS pct_within_18_complete_pairs,
       COUNT(*) FILTER (WHERE f.within_18_weeks IS NULL
                           OR f.total_incomplete_pathways IS NULL)
           AS missing_18week_count_rows
FROM fact_rtt f CROSS JOIN latest
WHERE f.reporting_month = latest.period
GROUP BY f.provider_code
ORDER BY over_52_weeks DESC NULLS LAST;
```

Discuss: provider size confounds raw long-wait counts; a burden share needs its
own paired coverage; published pathways are not unique patients; clinical urgency
is absent; source freshness and reporting changes matter.

## 20-minute Excel task

Import fact_rtt.csv through Data > From Text/CSV, set keys to Text and
reporting_month to Date, and load as table named RTT. Use the native Excel data
types; blanks in counts must remain blanks. Enter the chosen first-of-month date
in B2.

Create two helper columns in the RTT table:

```excel
Complete18
=AND(ISNUMBER([@within_18_weeks]),ISNUMBER([@total_incomplete_pathways]),[@total_incomplete_pathways]>0)

WeightedNumerator18
=IF([@Complete18],[@within_18_weeks],0)

WeightedDenominator18
=IF([@Complete18],[@total_incomplete_pathways],0)
```

Compute the selected month's rate with a guarded denominator:

```excel
=LET(n,SUMIFS(RTT[WeightedNumerator18],RTT[reporting_month],$B$2),
d,SUMIFS(RTT[WeightedDenominator18],RTT[reporting_month],$B$2),
IF(d=0,"No valid denominator",n/d))
```

Format the result as percentage. Add a PivotTable with provider rows, reporting
month filter and sums of counts. Keep latest waiting-list stock separate from
multi-month activity flow. Reconcile row count and selected-month counts to
manifest.json; inspect unmatched or missing keys before interpreting the result.

Test fixture: Service A has 1,000 pathways and 900 within 18 weeks; Service B has
100 and 10; Service C has 200 with a missing within-18 count.
Expected waiting list: 1,300. Complete-pair 18-week denominator: 1,100.
Expected rate: 82.727%. Missing count rows: 1. Rate coverage excludes C; disclose
this explicitly. The simple average of A and B percentages (50%) is wrong.

No Excel workbook has been supplied or tested in the native Excel engine.
