/**
 * TypeScript mirrors of the FastAPI Pydantic response models.
 * Kept in one file so a backend schema change surfaces as a type error.
 */

export type PriorityBand = "LOW" | "MODERATE" | "HIGH" | "CRITICAL" | "UNSCORED";

export interface DataProvenance {
  data_source_type: string;
  data_mode: string;
  is_demo: boolean;
  source_name: string;
  source_landing_page?: string | null;
  licence?: string | null;
  attribution?: string | null;
  latest_reporting_month?: string | null;
  latest_reporting_month_label?: string | null;
  reporting_months: number;
  earliest_reporting_month?: string | null;
  retrieved_at?: string | null;
  published_date?: string | null;
  built_at?: string | null;
  source_files: number;
}

export interface Metadata {
  app_name: string;
  app_version: string;
  provenance: DataProvenance;
  provider_count: number;
  specialty_count: number;
  fact_rows: number;
  quality_score?: number | null;
  referral_to_treatment_benchmark: number;
  min_waiting_list_for_ranking: number;
  forecast_summary: Record<string, unknown>;
  warehouse_available: boolean;
  notes: string[];
}

export interface Provider {
  provider_code: string;
  provider_name: string;
  provider_short_name?: string | null;
  region_code?: string | null;
  region_name?: string | null;
  provider_type?: string | null;
}

export interface Specialty {
  specialty_code: string;
  specialty_name: string;
  specialty_short_name?: string | null;
  specialty_group?: string | null;
}

export interface Region {
  region_code: string;
  region_name: string;
}

export interface ReportingPeriod {
  month_key: string;
  month_label: string;
  financial_year: string;
  is_latest: boolean;
}

export interface KpiCard {
  key: string;
  label: string;
  value: number | null;
  display_value: string;
  unit: string;
  secondary_label?: string | null;
  secondary_value?: number | null;
  secondary_display?: string | null;
  direction: "up" | "down" | "flat" | "none";
  higher_is_better?: boolean | null;
  definition: string;
  source: string;
  calculation: string;
}

export interface ScoreComponent {
  key: string;
  label: string;
  score: number | null;
  contribution: number | null;
  max_contribution: number;
  description: string;
}

export interface ServiceRow {
  provider_code: string;
  provider_name?: string | null;
  provider_short_name?: string | null;
  region_name?: string | null;
  specialty_code: string;
  specialty_name?: string | null;
  specialty_short_name?: string | null;
  specialty_group?: string | null;
  month_key?: string | null;

  total_incomplete_pathways?: number | null;
  within_18_weeks?: number | null;
  over_18_weeks?: number | null;
  over_52_weeks?: number | null;
  pct_within_18_weeks?: number | null;
  pct_over_18_weeks?: number | null;
  pct_over_52_weeks?: number | null;
  median_wait_weeks?: number | null;

  backlog_change_1m?: number | null;
  backlog_growth_1m_pct?: number | null;
  backlog_growth_3m_pct?: number | null;
  backlog_growth_6m_pct?: number | null;
  pct_within_18_weeks_change_3m?: number | null;
  months_backlog_rising?: number | null;
  trend_slope_6m?: number | null;

  completed_pathways?: number | null;
  rolling_activity_3m?: number | null;
  activity_change_3m_pct?: number | null;
  months_to_clear_at_current_activity?: number | null;

  forecast_status?: string | null;
  forecast_model?: string | null;
  forecast_confidence?: string | null;
  forecast_3m?: number | null;
  forecast_6m?: number | null;
  forecast_change_3m_pct?: number | null;
  forecast_change_6m_pct?: number | null;

  priority_score?: number | null;
  priority_band?: PriorityBand | null;
  priority_rank?: number | null;
  is_rankable: boolean;

  peer_median_pct_within_18_weeks?: number | null;
  peer_median_backlog_growth_3m_pct?: number | null;
  national_median_pct_within_18_weeks?: number | null;

  provider_quality_score?: number | null;
}

export interface AttentionCard {
  rank: number;
  provider_code: string;
  provider_name?: string | null;
  specialty_code: string;
  specialty_name?: string | null;
  priority_score?: number | null;
  priority_band?: PriorityBand | null;
  waiting_list?: number | null;
  reasons: string[];
}

export interface MatrixPoint {
  provider_code: string;
  provider_name?: string | null;
  specialty_code: string;
  specialty_name?: string | null;
  x_backlog_growth_3m_pct?: number | null;
  y_long_wait_pct?: number | null;
  size_waiting_list?: number | null;
  priority_band?: PriorityBand | null;
  priority_score?: number | null;
}

export interface TimeseriesPoint {
  month_key: string;
  month_label?: string | null;
  waiting_list?: number | null;
  within_18_weeks?: number | null;
  pct_within_18_weeks?: number | null;
  over_52_weeks?: number | null;
  pct_over_52_weeks?: number | null;
  completed_pathways?: number | null;
  admitted_activity?: number | null;
  non_admitted_activity?: number | null;
  is_forecast: boolean;
  forecast_lower?: number | null;
  forecast_upper?: number | null;
}

export interface TimeseriesResponse {
  scope: string;
  provider_code?: string | null;
  specialty_code?: string | null;
  label: string;
  points: TimeseriesPoint[];
}

export interface OverviewResponse {
  kpis: KpiCard[];
  attention: AttentionCard[];
  matrix: MatrixPoint[];
  national_trend: TimeseriesPoint[];
  /** Whether the trend series reflects the filter or the full population. */
  trend_scope: "filtered" | "national";
  band_counts: Record<string, number>;
  provenance: DataProvenance;
  filters_applied: Record<string, unknown>;
}

export interface RankingsResponse {
  total: number;
  returned: number;
  offset: number;
  limit: number;
  rows: ServiceRow[];
  filters_applied: Record<string, unknown>;
}

export interface ForecastPoint {
  horizon_months: number;
  month_key?: string | null;
  value?: number | null;
  lower?: number | null;
  upper?: number | null;
}

export interface ForecastAccuracy {
  mae?: number | null;
  rmse?: number | null;
  mape?: number | null;
  folds?: number | null;
  naive_mae?: number | null;
  skill_vs_naive?: number | null;
  beats_naive?: boolean | null;
}

export interface ForecastResponse {
  provider_code: string;
  specialty_code: string;
  status: string;
  model?: string | null;
  confidence: string;
  history_months: number;
  last_actual?: number | null;
  last_actual_month?: string | null;
  points: ForecastPoint[];
  accuracy?: ForecastAccuracy | null;
  message: string;
  method_note: string;
}

export interface ScenarioPointOut {
  horizon_months: number;
  month_key?: string | null;
  baseline_backlog: number;
  scenario_backlog: number;
  difference_from_baseline: number;
  additional_activity_cumulative: number;
}

export interface ScenarioSeries {
  uplift_pct: number;
  points: ScenarioPointOut[];
}

export interface ScenarioResponse {
  provider_code: string;
  provider_name?: string | null;
  specialty_code: string;
  specialty_name?: string | null;
  status: string;
  uplift_pct: number;
  baseline_monthly_activity?: number | null;
  additional_monthly_activity?: number | null;
  series: ScenarioSeries[];
  uplift_required_to_stabilise_pct?: number | null;
  stabilisation_feasible: boolean;
  assumptions: string[];
  disclaimer: string;
  message: string;
}

export interface BriefingSection {
  title: string;
  body: string;
}

export interface Briefing {
  headline: string;
  priority_band: string;
  priority_score?: number | null;
  sections: BriefingSection[];
  drivers: string[];
  recommended_actions: string[];
  caveats: string[];
  generated_by: string;
}

export interface ServiceDetailResponse {
  service: ServiceRow;
  score_components: ScoreComponent[];
  history: TimeseriesPoint[];
  forecast: ForecastResponse;
  scenario: ScenarioResponse;
  briefing: Briefing;
  quality_issues: Record<string, unknown>[];
  peer_context: Record<string, number | null>;
  provenance: DataProvenance;
}

export interface ProviderDetailResponse {
  provider: Provider;
  summary: Record<string, number | null>;
  services: ServiceRow[];
  history: TimeseriesPoint[];
  provenance: DataProvenance;
}

export interface ComparisonResponse {
  specialty_code: string;
  specialty_name?: string | null;
  providers: ServiceRow[];
  history: Record<string, TimeseriesPoint[]>;
  peer_median: Record<string, number | null>;
}

export interface QualityDimension {
  key: string;
  label: string;
  score: number;
  weight: number;
  contribution: number;
  description: string;
}

export interface QualityIssueRow {
  provider_code?: string | null;
  provider_name?: string | null;
  specialty_code?: string | null;
  specialty_name?: string | null;
  month?: string | null;
  issue_type: string;
  severity: string;
  description: string;
  observed_value?: number | null;
  expected_value?: number | null;
}

export interface DataQualityResponse {
  overall_score: number;
  dimensions: QualityDimension[];
  metrics: Record<string, unknown>;
  issues: QualityIssueRow[];
  total_issues: number;
  returned_issues: number;
  issue_type_counts: Record<string, number>;
  severity_counts: Record<string, number>;
  provenance: DataProvenance;
}

export interface MethodologySection {
  key: string;
  title: string;
  body: string;
  bullets: string[];
  formula?: string | null;
}

export interface MethodologyResponse {
  sections: MethodologySection[];
  priority_components: Array<{
    key: string;
    label: string;
    weight: number;
    description: string;
  }>;
  priority_bands: Array<{ band: string; min_score: number; max_score: number }>;
  quality_weights: Record<string, number>;
  forecast_summary: Record<string, unknown>;
  limitations: string[];
  provenance: DataProvenance;
}
