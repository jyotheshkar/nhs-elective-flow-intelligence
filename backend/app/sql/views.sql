-- ---------------------------------------------------------------------------
-- NHS Elective Flow Intelligence - analytical views
-- ---------------------------------------------------------------------------
-- These views are the API's read surface. Aggregation happens here so the
-- frontend receives decision-ready rows rather than raw facts.
-- ---------------------------------------------------------------------------

-- The full monthly panel, enriched with provider and specialty attributes.
CREATE OR REPLACE VIEW vw_provider_specialty_trends AS
SELECT
    m.provider_code,
    p.provider_name,
    p.provider_short_name,
    p.region_code,
    p.region_name,
    p.provider_type,
    m.specialty_code,
    s.specialty_name,
    s.specialty_short_name,
    s.specialty_group,
    m.reporting_month,
    m.month_key,
    m.total_incomplete_pathways,
    m.within_18_weeks,
    m.over_18_weeks,
    m.over_52_weeks,
    m.over_65_weeks,
    m.over_78_weeks,
    m.pct_within_18_weeks,
    m.pct_over_18_weeks,
    m.pct_over_52_weeks,
    m.median_wait_weeks,
    m.admitted_activity,
    m.non_admitted_activity,
    m.completed_pathways,
    m.backlog_change_1m,
    m.backlog_growth_1m_pct,
    m.backlog_growth_3m_pct,
    m.backlog_growth_6m_pct,
    m.waiting_list_rolling_3m,
    m.trend_slope_3m,
    m.trend_slope_6m,
    m.months_backlog_rising,
    m.share_months_rising_6m,
    m.rolling_activity_3m,
    m.activity_change_3m_pct,
    m.months_to_clear_at_current_activity,
    m.implied_additions,
    m.activity_gap_pct,
    m.data_source_type
FROM fact_rtt_metrics AS m
LEFT JOIN dim_provider  AS p ON p.provider_code  = m.provider_code
LEFT JOIN dim_specialty AS s ON s.specialty_code = m.specialty_code;


-- Latest reporting month only, with priority scores and forecasts attached.
-- This is the workhorse view behind the dashboard, rankings and detail pages.
CREATE OR REPLACE VIEW vw_latest_performance AS
SELECT
    pr.*,
    p.provider_name,
    p.provider_short_name,
    p.region_code,
    p.region_name,
    p.provider_type,
    s.specialty_name,
    s.specialty_short_name,
    s.specialty_group,
    q.provider_quality_score,
    q.quality_issues        AS provider_quality_issues,
    q.high_severity_issues  AS provider_high_severity_issues
FROM fact_priority AS pr
LEFT JOIN dim_provider          AS p ON p.provider_code  = pr.provider_code
LEFT JOIN dim_specialty         AS s ON s.specialty_code = pr.specialty_code
LEFT JOIN dim_provider_quality  AS q ON q.provider_code  = pr.provider_code;


-- Ranked services: the "where should attention go first?" answer.
CREATE OR REPLACE VIEW vw_priority_scores AS
SELECT
    *,
    ROW_NUMBER() OVER (ORDER BY priority_score DESC, total_incomplete_pathways DESC)
        AS overall_rank
FROM vw_latest_performance
WHERE is_rankable;


-- Provider roll-up for the provider view and region filters.
CREATE OR REPLACE VIEW vw_provider_summary AS
SELECT
    provider_code,
    ANY_VALUE(provider_name)       AS provider_name,
    ANY_VALUE(provider_short_name) AS provider_short_name,
    ANY_VALUE(region_name)         AS region_name,
    ANY_VALUE(provider_type)       AS provider_type,
    COUNT(*)                                    AS specialty_count,
    SUM(total_incomplete_pathways)              AS waiting_list,
    SUM(within_18_weeks)                        AS within_18_weeks,
    SUM(over_52_weeks)                          AS over_52_weeks,
    SUM(completed_pathways)                     AS completed_pathways,
    -- Weighted, not averaged: a provider's 18-week position is the ratio of
    -- its totals, not the mean of its specialty percentages.
    CASE WHEN SUM(total_incomplete_pathways) > 0
         THEN SUM(within_18_weeks) * 100.0 / SUM(total_incomplete_pathways)
    END AS pct_within_18_weeks,
    CASE WHEN SUM(total_incomplete_pathways) > 0
         THEN SUM(over_52_weeks) * 100.0 / SUM(total_incomplete_pathways)
    END AS pct_over_52_weeks,
    MAX(priority_score)                         AS max_priority_score,
    AVG(priority_score)                         AS avg_priority_score,
    SUM(CASE WHEN priority_band IN ('HIGH', 'CRITICAL') THEN 1 ELSE 0 END)
        AS high_priority_specialties,
    ANY_VALUE(provider_quality_score)           AS provider_quality_score
FROM vw_latest_performance
GROUP BY provider_code;


-- National monthly position, for the headline trend chart.
CREATE OR REPLACE VIEW vw_national_trend AS
SELECT
    reporting_month,
    month_key,
    SUM(total_incomplete_pathways) AS waiting_list,
    SUM(within_18_weeks)           AS within_18_weeks,
    SUM(over_52_weeks)             AS over_52_weeks,
    SUM(completed_pathways)        AS completed_pathways,
    CASE WHEN SUM(total_incomplete_pathways) > 0
         THEN SUM(within_18_weeks) * 100.0 / SUM(total_incomplete_pathways)
    END AS pct_within_18_weeks,
    CASE WHEN SUM(total_incomplete_pathways) > 0
         THEN SUM(over_52_weeks) * 100.0 / SUM(total_incomplete_pathways)
    END AS pct_over_52_weeks,
    COUNT(DISTINCT provider_code)  AS provider_count,
    COUNT(*)                       AS series_count
FROM vw_provider_specialty_trends
GROUP BY reporting_month, month_key
ORDER BY reporting_month;


-- Specialty roll-up across all providers in the latest month.
CREATE OR REPLACE VIEW vw_specialty_summary AS
SELECT
    specialty_code,
    ANY_VALUE(specialty_name)       AS specialty_name,
    ANY_VALUE(specialty_short_name) AS specialty_short_name,
    ANY_VALUE(specialty_group)      AS specialty_group,
    COUNT(*)                        AS provider_count,
    SUM(total_incomplete_pathways)  AS waiting_list,
    SUM(over_52_weeks)              AS over_52_weeks,
    CASE WHEN SUM(total_incomplete_pathways) > 0
         THEN SUM(within_18_weeks) * 100.0 / SUM(total_incomplete_pathways)
    END AS pct_within_18_weeks,
    AVG(priority_score)             AS avg_priority_score,
    MEDIAN(backlog_growth_3m_pct)   AS median_backlog_growth_3m_pct,
    SUM(CASE WHEN priority_band IN ('HIGH', 'CRITICAL') THEN 1 ELSE 0 END)
        AS high_priority_providers
FROM vw_latest_performance
GROUP BY specialty_code;


-- Data quality issues joined to readable labels.
CREATE OR REPLACE VIEW vw_data_quality AS
SELECT
    i.*,
    p.region_name,
    p.provider_short_name
FROM fact_quality_issues AS i
LEFT JOIN dim_provider AS p ON p.provider_code = i.provider_code;
