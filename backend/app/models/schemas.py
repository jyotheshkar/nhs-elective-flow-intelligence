"""Pydantic response and request models for the public API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    """Base model: rejects unknown request fields, allows population by name."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --- Metadata & provenance --------------------------------------------------
class DataProvenance(ApiModel):
    """Where the loaded numbers came from. Displayed throughout the UI."""

    data_source_type: str = Field(
        description="OFFICIAL_NHS_PUBLIC or DEMO_SYNTHETIC."
    )
    data_mode: str
    is_demo: bool
    source_name: str
    source_landing_page: str | None = None
    licence: str | None = None
    attribution: str | None = None
    latest_reporting_month: str | None = None
    latest_reporting_month_label: str | None = None
    reporting_months: int
    earliest_reporting_month: str | None = None
    retrieved_at: str | None = None
    published_date: str | None = None
    built_at: str | None = None
    source_files: int = 0


class Metadata(ApiModel):
    """Everything the frontend needs to render filters and provenance."""

    app_name: str
    app_version: str
    provenance: DataProvenance
    provider_count: int
    specialty_count: int
    fact_rows: int
    quality_score: float | None = None
    referral_to_treatment_benchmark: float
    min_waiting_list_for_ranking: int
    forecast_summary: dict[str, Any] = Field(default_factory=dict)
    warehouse_available: bool = True
    notes: list[str] = Field(default_factory=list)


class HealthResponse(ApiModel):
    status: Literal["ok", "degraded"]
    app_version: str
    warehouse_available: bool
    data_mode: str
    tables: dict[str, int] = Field(default_factory=dict)
    message: str = ""


# --- Reference data ---------------------------------------------------------
class Provider(ApiModel):
    provider_code: str
    provider_name: str
    provider_short_name: str | None = None
    region_code: str | None = None
    region_name: str | None = None
    provider_type: str | None = None


class Specialty(ApiModel):
    specialty_code: str
    specialty_name: str
    specialty_short_name: str | None = None
    specialty_group: str | None = None


class ReportingPeriod(ApiModel):
    month_key: str
    month_label: str
    financial_year: str
    is_latest: bool


class Region(ApiModel):
    region_code: str
    region_name: str


# --- Core analytics ---------------------------------------------------------
class KpiCard(ApiModel):
    """One executive KPI, with its definition attached for the tooltip."""

    key: str
    label: str
    value: float | None
    display_value: str
    unit: str
    secondary_label: str | None = None
    secondary_value: float | None = None
    secondary_display: str | None = None
    direction: Literal["up", "down", "flat", "none"] = "none"
    # Whether an increase is good or bad, so the UI colours it correctly.
    higher_is_better: bool | None = None
    definition: str
    source: str
    calculation: str


class ScoreComponent(ApiModel):
    key: str
    label: str
    score: float | None
    contribution: float | None
    max_contribution: float
    description: str


class ServiceRow(ApiModel):
    """One provider x specialty in the latest reporting month."""

    provider_code: str
    provider_name: str | None = None
    provider_short_name: str | None = None
    region_name: str | None = None
    specialty_code: str
    specialty_name: str | None = None
    specialty_short_name: str | None = None
    specialty_group: str | None = None
    month_key: str | None = None

    total_incomplete_pathways: float | None = None
    within_18_weeks: float | None = None
    over_18_weeks: float | None = None
    over_52_weeks: float | None = None
    pct_within_18_weeks: float | None = None
    pct_over_18_weeks: float | None = None
    pct_over_52_weeks: float | None = None
    median_wait_weeks: float | None = None

    backlog_change_1m: float | None = None
    backlog_growth_1m_pct: float | None = None
    backlog_growth_3m_pct: float | None = None
    backlog_growth_6m_pct: float | None = None
    pct_within_18_weeks_change_3m: float | None = None
    months_backlog_rising: float | None = None
    trend_slope_6m: float | None = None

    completed_pathways: float | None = None
    rolling_activity_3m: float | None = None
    activity_change_3m_pct: float | None = None
    months_to_clear_at_current_activity: float | None = None

    forecast_status: str | None = None
    forecast_model: str | None = None
    forecast_confidence: str | None = None
    forecast_3m: float | None = None
    forecast_6m: float | None = None
    forecast_change_3m_pct: float | None = None
    forecast_change_6m_pct: float | None = None

    priority_score: float | None = None
    priority_band: str | None = None
    priority_rank: float | None = None
    is_rankable: bool = True

    peer_median_pct_within_18_weeks: float | None = None
    peer_median_backlog_growth_3m_pct: float | None = None
    national_median_pct_within_18_weeks: float | None = None

    provider_quality_score: float | None = None


class RankingsResponse(ApiModel):
    total: int
    returned: int
    offset: int
    limit: int
    rows: list[ServiceRow]
    filters_applied: dict[str, Any] = Field(default_factory=dict)


class AttentionCard(ApiModel):
    rank: int
    provider_code: str
    provider_name: str | None = None
    specialty_code: str
    specialty_name: str | None = None
    priority_score: float | None = None
    priority_band: str | None = None
    waiting_list: float | None = None
    reasons: list[str] = Field(default_factory=list)


class MatrixPoint(ApiModel):
    """One bubble on the priority matrix."""

    provider_code: str
    provider_name: str | None = None
    specialty_code: str
    specialty_name: str | None = None
    x_backlog_growth_3m_pct: float | None = None
    y_long_wait_pct: float | None = None
    size_waiting_list: float | None = None
    priority_band: str | None = None
    priority_score: float | None = None


class TimeseriesPoint(ApiModel):
    month_key: str
    month_label: str | None = None
    waiting_list: float | None = None
    within_18_weeks: float | None = None
    pct_within_18_weeks: float | None = None
    over_52_weeks: float | None = None
    pct_over_52_weeks: float | None = None
    completed_pathways: float | None = None
    admitted_activity: float | None = None
    non_admitted_activity: float | None = None
    is_forecast: bool = False
    forecast_lower: float | None = None
    forecast_upper: float | None = None


class TimeseriesResponse(ApiModel):
    scope: str
    provider_code: str | None = None
    specialty_code: str | None = None
    label: str
    points: list[TimeseriesPoint]


class OverviewResponse(ApiModel):
    kpis: list[KpiCard]
    attention: list[AttentionCard]
    matrix: list[MatrixPoint]
    national_trend: list[TimeseriesPoint]
    band_counts: dict[str, int]
    provenance: DataProvenance
    filters_applied: dict[str, Any] = Field(default_factory=dict)


# --- Forecast ---------------------------------------------------------------
class ForecastPoint(ApiModel):
    horizon_months: int
    month_key: str | None = None
    value: float | None = None
    lower: float | None = None
    upper: float | None = None


class ForecastAccuracy(ApiModel):
    mae: float | None = None
    rmse: float | None = None
    mape: float | None = None
    folds: int | None = None
    naive_mae: float | None = None
    skill_vs_naive: float | None = None
    beats_naive: bool | None = None


class ForecastResponse(ApiModel):
    provider_code: str
    specialty_code: str
    status: str
    model: str | None = None
    confidence: str
    history_months: int
    last_actual: float | None = None
    last_actual_month: str | None = None
    points: list[ForecastPoint] = Field(default_factory=list)
    accuracy: ForecastAccuracy | None = None
    message: str = ""
    method_note: str


# --- Scenario ---------------------------------------------------------------
class ScenarioRequest(ApiModel):
    provider_code: str = Field(min_length=1, max_length=16)
    specialty_code: str = Field(min_length=1, max_length=16)
    uplift_pct: float = Field(
        default=10.0, ge=0.0, le=100.0,
        description="Assumed percentage increase in monthly completed activity.",
    )
    compare_uplifts: list[float] | None = Field(
        default=None,
        description="Optional additional uplift percentages to evaluate.",
    )


class ScenarioPointOut(ApiModel):
    horizon_months: int
    month_key: str | None = None
    baseline_backlog: float
    scenario_backlog: float
    difference_from_baseline: float
    additional_activity_cumulative: float


class ScenarioSeries(ApiModel):
    uplift_pct: float
    points: list[ScenarioPointOut]


class ScenarioResponse(ApiModel):
    provider_code: str
    provider_name: str | None = None
    specialty_code: str
    specialty_name: str | None = None
    status: str
    uplift_pct: float
    baseline_monthly_activity: float | None = None
    additional_monthly_activity: float | None = None
    series: list[ScenarioSeries] = Field(default_factory=list)
    uplift_required_to_stabilise_pct: float | None = None
    stabilisation_feasible: bool = False
    assumptions: list[str] = Field(default_factory=list)
    disclaimer: str
    message: str = ""


# --- Service detail ---------------------------------------------------------
class BriefingSection(ApiModel):
    title: str
    body: str


class Briefing(ApiModel):
    headline: str
    priority_band: str
    priority_score: float | None = None
    sections: list[BriefingSection]
    drivers: list[str]
    recommended_actions: list[str]
    caveats: list[str]
    generated_by: str


class ServiceDetailResponse(ApiModel):
    service: ServiceRow
    score_components: list[ScoreComponent]
    history: list[TimeseriesPoint]
    forecast: ForecastResponse
    scenario: ScenarioResponse
    briefing: Briefing
    quality_issues: list[dict[str, Any]] = Field(default_factory=list)
    peer_context: dict[str, Any] = Field(default_factory=dict)
    provenance: DataProvenance


class ProviderDetailResponse(ApiModel):
    provider: Provider
    summary: dict[str, Any]
    services: list[ServiceRow]
    history: list[TimeseriesPoint]
    provenance: DataProvenance


class ComparisonResponse(ApiModel):
    specialty_code: str
    specialty_name: str | None = None
    providers: list[ServiceRow]
    history: dict[str, list[TimeseriesPoint]]
    peer_median: dict[str, float | None] = Field(default_factory=dict)


# --- Data quality -----------------------------------------------------------
class QualityDimension(ApiModel):
    key: str
    label: str
    score: float
    weight: float
    contribution: float
    description: str


class QualityIssueRow(ApiModel):
    provider_code: str | None = None
    provider_name: str | None = None
    specialty_code: str | None = None
    specialty_name: str | None = None
    month: str | None = None
    issue_type: str
    severity: str
    description: str
    observed_value: float | None = None
    expected_value: float | None = None


class DataQualityResponse(ApiModel):
    overall_score: float
    dimensions: list[QualityDimension]
    metrics: dict[str, Any]
    issues: list[QualityIssueRow]
    total_issues: int
    returned_issues: int
    issue_type_counts: dict[str, int] = Field(default_factory=dict)
    severity_counts: dict[str, int] = Field(default_factory=dict)
    provenance: DataProvenance


# --- Methodology ------------------------------------------------------------
class MethodologySection(ApiModel):
    key: str
    title: str
    body: str
    bullets: list[str] = Field(default_factory=list)
    formula: str | None = None


class MethodologyResponse(ApiModel):
    sections: list[MethodologySection]
    priority_components: list[dict[str, Any]]
    priority_bands: list[dict[str, Any]]
    quality_weights: dict[str, float]
    forecast_summary: dict[str, Any]
    limitations: list[str]
    provenance: DataProvenance
