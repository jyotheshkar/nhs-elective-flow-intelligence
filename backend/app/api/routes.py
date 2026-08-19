"""Public API routes."""

from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.analytics.narrative import build_attention_cards, build_service_briefing
from app.analytics.priority import COMPONENTS, band_metadata, component_metadata
from app.api import repository as repo
from app.api.filters import SORTABLE_COLUMNS, apply_filters, apply_sort
from app.api.kpis import build_kpis
from app.api.methodology import build_methodology
from app.config import get_settings
from app.models.schemas import (
    AttentionCard,
    Briefing,
    BriefingSection,
    ComparisonResponse,
    DataProvenance,
    DataQualityResponse,
    ForecastAccuracy,
    ForecastPoint,
    ForecastResponse,
    MatrixPoint,
    Metadata,
    MethodologyResponse,
    OverviewResponse,
    Provider,
    ProviderDetailResponse,
    QualityDimension,
    QualityIssueRow,
    RankingsResponse,
    Region,
    ReportingPeriod,
    ScenarioRequest,
    ScenarioResponse,
    ScenarioSeries,
    ScoreComponent,
    ServiceDetailResponse,
    ServiceRow,
    Specialty,
    TimeseriesPoint,
    TimeseriesResponse,
)
from app.quality.score import WEIGHTS as QUALITY_WEIGHTS
from app.scenarios.engine import DEFAULT_UPLIFTS, run_scenario, scenario_assumptions
from app.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

SCENARIO_DISCLAIMER = (
    "Illustrative capacity scenario, not a causal prediction. Figures are "
    "modelled estimates produced by an accounting projection under stated "
    "assumptions."
)

FORECAST_METHOD_NOTE = (
    "Candidate models (naive drift, linear trend, Holt linear, damped trend) "
    "are compared by rolling-origin out-of-sample error; the lowest-error model "
    "is selected and refitted on the full series. Intervals are indicative 80% "
    "bands, not rigorous confidence intervals."
)


# --- Helpers ----------------------------------------------------------------
def _provenance() -> DataProvenance:
    return DataProvenance(**repo.build_provenance())


def _service_rows(frame: pd.DataFrame) -> list[ServiceRow]:
    allowed = set(ServiceRow.model_fields.keys())
    rows: list[ServiceRow] = []
    for record in repo.records(frame):
        rows.append(ServiceRow(**{k: v for k, v in record.items() if k in allowed}))
    return rows


def _history_points(frame: pd.DataFrame) -> list[TimeseriesPoint]:
    """Convert a monthly frame into chart points.

    The waiting-list measure arrives under two names depending on the source:
    ``total_incomplete_pathways`` at service grain, and ``waiting_list`` from
    the pre-aggregated national/provider views. Accepting both keeps the views
    free to name their aggregates naturally - reading only one name silently
    produced a chart with axes but no line.
    """
    points: list[TimeseriesPoint] = []
    for record in repo.records(frame):
        month = record.get("month_key")
        if not month:
            continue
        waiting_list = record.get("total_incomplete_pathways")
        if waiting_list is None:
            waiting_list = record.get("waiting_list")
        points.append(
            TimeseriesPoint(
                month_key=str(month),
                month_label=_month_label(str(month)),
                waiting_list=waiting_list,
                within_18_weeks=record.get("within_18_weeks"),
                pct_within_18_weeks=record.get("pct_within_18_weeks"),
                over_52_weeks=record.get("over_52_weeks"),
                pct_over_52_weeks=record.get("pct_over_52_weeks"),
                completed_pathways=record.get("completed_pathways"),
                admitted_activity=record.get("admitted_activity"),
                non_admitted_activity=record.get("non_admitted_activity"),
                is_forecast=False,
            )
        )
    return points


def _month_label(month_key: str) -> str:
    try:
        return pd.Timestamp(f"{month_key}-01").strftime("%b %Y")
    except (ValueError, TypeError):
        return month_key


def _forecast_response(
    provider_code: str, specialty_code: str, row: dict[str, Any]
) -> ForecastResponse:
    status = str(row.get("forecast_status") or "insufficient_history")
    points: list[ForecastPoint] = []
    if status == "ok":
        for horizon in (1, 3, 6):
            value = row.get(f"forecast_{horizon}m")
            if value is None:
                continue
            points.append(
                ForecastPoint(
                    horizon_months=horizon,
                    month_key=row.get(f"forecast_{horizon}m_month"),
                    value=value,
                    lower=row.get(f"forecast_{horizon}m_lower"),
                    upper=row.get(f"forecast_{horizon}m_upper"),
                )
            )

    accuracy = None
    if row.get("backtest_mae") is not None:
        skill = row.get("backtest_skill_vs_naive")
        accuracy = ForecastAccuracy(
            mae=row.get("backtest_mae"),
            rmse=row.get("backtest_rmse"),
            mape=row.get("backtest_mape"),
            folds=int(row["backtest_folds"]) if row.get("backtest_folds") else None,
            naive_mae=row.get("backtest_naive_mae"),
            skill_vs_naive=skill,
            beats_naive=bool(skill > 0) if skill is not None else None,
        )

    return ForecastResponse(
        provider_code=provider_code,
        specialty_code=specialty_code,
        status=status,
        model=row.get("forecast_model"),
        confidence=str(row.get("forecast_confidence") or "Insufficient data"),
        history_months=int(row.get("forecast_history_months") or 0),
        last_actual=row.get("forecast_last_actual"),
        last_actual_month=row.get("forecast_1m_month"),
        points=points,
        accuracy=accuracy,
        message=str(row.get("forecast_message") or ""),
        method_note=FORECAST_METHOD_NOTE,
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=what)


# --- Metadata ---------------------------------------------------------------
@router.get("/metadata", response_model=Metadata, tags=["metadata"])
def get_metadata() -> Metadata:
    """Application metadata, provenance and reference counts."""
    settings = get_settings()
    if not repo.warehouse_available():
        return Metadata(
            app_name=settings.app_name,
            app_version=settings.app_version,
            provenance=_provenance(),
            provider_count=0,
            specialty_count=0,
            fact_rows=0,
            referral_to_treatment_benchmark=settings.referral_to_treatment_benchmark,
            min_waiting_list_for_ranking=settings.min_waiting_list_for_ranking,
            warehouse_available=False,
            notes=[
                "Official data is currently unavailable. Run 'make data' to "
                "build the warehouse, or 'make demo' for the synthetic dataset."
            ],
        )

    meta = repo.load_metadata()
    notes = [m for m in str(meta.get("build_messages") or "").split(" | ") if m]
    return Metadata(
        app_name=settings.app_name,
        app_version=settings.app_version,
        provenance=_provenance(),
        provider_count=int(meta.get("provider_count") or 0),
        specialty_count=int(meta.get("specialty_count") or 0),
        fact_rows=int(meta.get("fact_rows") or 0),
        quality_score=meta.get("quality_score"),
        referral_to_treatment_benchmark=float(
            meta.get("referral_to_treatment_benchmark")
            or settings.referral_to_treatment_benchmark
        ),
        min_waiting_list_for_ranking=int(
            meta.get("min_waiting_list_for_ranking")
            or settings.min_waiting_list_for_ranking
        ),
        forecast_summary={
            "series_ok": meta.get("forecast_series_ok"),
            "series_insufficient": meta.get("forecast_series_insufficient"),
            "median_mape": meta.get("forecast_median_mape"),
            "share_beating_naive": meta.get("forecast_share_beating_naive"),
        },
        warehouse_available=True,
        notes=notes,
    )


@router.get("/providers", response_model=list[Provider], tags=["reference"])
def get_providers() -> list[Provider]:
    """All provider organisations in the loaded dataset."""
    repo.require_warehouse()
    return [Provider(**r) for r in repo.records(repo.load_providers())]


@router.get("/specialties", response_model=list[Specialty], tags=["reference"])
def get_specialties() -> list[Specialty]:
    """All treatment functions in the loaded dataset."""
    repo.require_warehouse()
    return [Specialty(**r) for r in repo.records(repo.load_specialties())]


@router.get("/regions", response_model=list[Region], tags=["reference"])
def get_regions() -> list[Region]:
    """NHS England regions present in the loaded dataset."""
    repo.require_warehouse()
    return [Region(**r) for r in repo.records(repo.load_regions())]


@router.get(
    "/reporting-periods", response_model=list[ReportingPeriod], tags=["reference"]
)
def get_reporting_periods() -> list[ReportingPeriod]:
    """Reporting months available, newest first."""
    repo.require_warehouse()
    periods = repo.load_periods()
    return [
        ReportingPeriod(
            month_key=r["month_key"],
            month_label=r["month_label"],
            financial_year=r["financial_year"],
            is_latest=bool(r["is_latest"]),
        )
        for r in repo.records(periods)
    ]


# --- Overview ---------------------------------------------------------------
@router.get("/overview", response_model=OverviewResponse, tags=["analytics"])
def get_overview(
    provider_code: str | None = Query(None, max_length=16),
    specialty_code: str | None = Query(None, max_length=16),
    region: str | None = Query(None, max_length=64),
    priority_band: str | None = Query(None, max_length=16),
    search: str | None = Query(None, max_length=120),
    attention_limit: int = Query(5, ge=1, le=20),
    matrix_limit: int = Query(400, ge=10, le=2000),
) -> OverviewResponse:
    """Executive KPIs, priority matrix, attention cards and national trend."""
    repo.require_warehouse()
    snapshot = repo.load_snapshot()
    filtered, applied = apply_filters(
        snapshot, provider_code, specialty_code, region, priority_band, search
    )

    if filtered.empty:
        return OverviewResponse(
            kpis=[],
            attention=[],
            matrix=[],
            national_trend=_history_points(repo.load_national_trend()),
            band_counts={},
            provenance=_provenance(),
            filters_applied=applied,
        )

    quality_score = repo.load_metadata().get("quality_score")
    kpis = build_kpis(filtered, repo.load_national_trend(), quality_score)

    rankable = filtered[filtered.get("is_rankable", True)]
    basis = rankable if not rankable.empty else filtered
    ranked = basis.sort_values("priority_score", ascending=False)
    attention = [
        AttentionCard(**card)
        for card in build_attention_cards(ranked, limit=attention_limit)
    ]

    # Matrix: cap the point count so the browser is not asked to render
    # thousands of bubbles. The largest lists are the ones worth plotting.
    matrix_source = basis.nlargest(matrix_limit, "total_incomplete_pathways")
    long_wait_column = (
        "pct_over_52_weeks"
        if "pct_over_52_weeks" in matrix_source.columns
        and matrix_source["pct_over_52_weeks"].fillna(0).max() > 0
        else "pct_over_18_weeks"
    )
    matrix = [
        MatrixPoint(
            provider_code=r["provider_code"],
            provider_name=r.get("provider_short_name") or r.get("provider_name"),
            specialty_code=r["specialty_code"],
            specialty_name=r.get("specialty_short_name") or r.get("specialty_name"),
            x_backlog_growth_3m_pct=r.get("backlog_growth_3m_pct"),
            y_long_wait_pct=r.get(long_wait_column),
            size_waiting_list=r.get("total_incomplete_pathways"),
            priority_band=r.get("priority_band"),
            priority_score=r.get("priority_score"),
        )
        for r in repo.records(matrix_source)
    ]

    band_counts = (
        filtered["priority_band"].value_counts().to_dict()
        if "priority_band" in filtered.columns
        else {}
    )

    # The trend chart follows the filter when one is applied, so the chart and
    # the KPIs describe the same population. Very broad selections fall back to
    # the national series, and the scope is returned so the UI can say which.
    trend, trend_scope = (
        _filtered_trend(filtered) if applied
        else (_history_points(repo.load_national_trend()), "national")
    )

    return OverviewResponse(
        kpis=kpis,
        attention=attention,
        matrix=matrix,
        national_trend=trend,
        trend_scope=trend_scope,
        band_counts={str(k): int(v) for k, v in band_counts.items()},
        provenance=_provenance(),
        filters_applied=applied,
    )


def _filtered_trend(
    filtered: pd.DataFrame,
) -> tuple[list[TimeseriesPoint], str]:
    """Aggregate monthly history for the currently filtered services.

    Returns the points *and the scope actually used*, so the caller never
    presents the national series as though it were the filtered one.
    """
    pairs = list(
        zip(
            filtered["provider_code"].tolist(),
            filtered["specialty_code"].tolist(),
            strict=True,
        )
    )
    if not pairs or len(pairs) > 600:
        # Too many series to assemble cheaply; fall back to the national view
        # and say so.
        return _history_points(repo.load_national_trend()), "national"

    frames = [repo.load_service_history(p, s) for p, s in pairs]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return [], "filtered"
    stacked = pd.concat(frames, ignore_index=True)
    grouped = (
        stacked.groupby("month_key", as_index=False)
        .agg(
            total_incomplete_pathways=("total_incomplete_pathways", "sum"),
            within_18_weeks=("within_18_weeks", "sum"),
            over_52_weeks=("over_52_weeks", "sum"),
            completed_pathways=("completed_pathways", "sum"),
        )
        .sort_values("month_key")
    )
    grouped["pct_within_18_weeks"] = np.where(
        grouped["total_incomplete_pathways"] > 0,
        grouped["within_18_weeks"] / grouped["total_incomplete_pathways"] * 100.0,
        np.nan,
    )
    grouped["pct_over_52_weeks"] = np.where(
        grouped["total_incomplete_pathways"] > 0,
        grouped["over_52_weeks"] / grouped["total_incomplete_pathways"] * 100.0,
        np.nan,
    )
    return _history_points(grouped), "filtered"


# --- Rankings ---------------------------------------------------------------
@router.get("/rankings", response_model=RankingsResponse, tags=["analytics"])
def get_rankings(
    provider_code: str | None = Query(None, max_length=16),
    specialty_code: str | None = Query(None, max_length=16),
    region: str | None = Query(None, max_length=64),
    priority_band: str | None = Query(None, max_length=16),
    search: str | None = Query(None, max_length=120),
    sort_by: str = Query("priority_score"),
    descending: bool = Query(True),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    rankable_only: bool = Query(True),
) -> RankingsResponse:
    """Ranked provider x specialty table with sorting and pagination."""
    repo.require_warehouse()
    if sort_by not in SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"'{sort_by}' is not a sortable column. Allowed: "
                f"{sorted(SORTABLE_COLUMNS)}"
            ),
        )

    snapshot = repo.load_snapshot()
    filtered, applied = apply_filters(
        snapshot, provider_code, specialty_code, region, priority_band, search,
        rankable_only=rankable_only,
    )
    ordered = apply_sort(filtered, sort_by, descending)
    page = ordered.iloc[offset: offset + limit]

    return RankingsResponse(
        total=int(len(ordered)),
        returned=int(len(page)),
        offset=offset,
        limit=limit,
        rows=_service_rows(page),
        filters_applied={**applied, "sort_by": sort_by, "descending": descending},
    )


@router.get("/rankings/export", tags=["analytics"])
def export_rankings(
    provider_code: str | None = Query(None, max_length=16),
    specialty_code: str | None = Query(None, max_length=16),
    region: str | None = Query(None, max_length=64),
    priority_band: str | None = Query(None, max_length=16),
    search: str | None = Query(None, max_length=120),
    sort_by: str = Query("priority_score"),
    descending: bool = Query(True),
    rankable_only: bool = Query(True),
) -> StreamingResponse:
    """Download the currently filtered ranking as CSV."""
    repo.require_warehouse()
    snapshot = repo.load_snapshot()
    filtered, _ = apply_filters(
        snapshot, provider_code, specialty_code, region, priority_band, search,
        rankable_only=rankable_only,
    )
    ordered = apply_sort(filtered, sort_by, descending)

    columns = [
        "provider_code", "provider_name", "region_name", "specialty_code",
        "specialty_name", "month_key", "priority_score", "priority_band",
        "total_incomplete_pathways", "within_18_weeks", "pct_within_18_weeks",
        "over_52_weeks", "pct_over_52_weeks", "median_wait_weeks",
        "backlog_change_1m", "backlog_growth_3m_pct", "backlog_growth_6m_pct",
        "months_backlog_rising", "completed_pathways", "rolling_activity_3m",
        "forecast_status", "forecast_model", "forecast_confidence",
        "forecast_3m", "forecast_change_3m_pct",
        "score_backlog_pressure", "score_long_wait_burden",
        "score_performance_gap", "score_forecast_risk", "score_persistence",
        "data_source_type",
    ]
    available = [c for c in columns if c in ordered.columns]
    export = ordered[available]

    buffer = io.StringIO()
    provenance = repo.build_provenance()
    buffer.write(
        f"# NHS Elective Flow Intelligence - ranked services export\n"
        f"# Data source type: {provenance.get('data_source_type')}\n"
        f"# Latest reporting month: "
        f"{provenance.get('latest_reporting_month_label')}\n"
        f"# Source: {provenance.get('source_name')}\n"
        f"# Note: priority scores and forecasts are derived measures produced "
        f"by this application, not published NHS England statistics.\n"
    )
    export.to_csv(buffer, index=False)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                "attachment; filename=nhs-elective-flow-rankings.csv"
            )
        },
    )


# --- Time series ------------------------------------------------------------
@router.get("/timeseries", response_model=TimeseriesResponse, tags=["analytics"])
def get_timeseries(
    provider_code: str | None = Query(None, max_length=16),
    specialty_code: str | None = Query(None, max_length=16),
    include_forecast: bool = Query(False),
) -> TimeseriesResponse:
    """Monthly history at national, provider or service scope."""
    repo.require_warehouse()

    if provider_code and specialty_code:
        history = repo.load_service_history(provider_code, specialty_code)
        if history.empty:
            raise _not_found(
                f"No data for provider '{provider_code}' and specialty "
                f"'{specialty_code}'."
            )
        points = _history_points(history)
        if include_forecast:
            points.extend(
                _forecast_points(repo.load_forecast_row(provider_code, specialty_code))
            )
        return TimeseriesResponse(
            scope="service",
            provider_code=provider_code,
            specialty_code=specialty_code,
            label="Provider and specialty",
            points=points,
        )

    if provider_code:
        history = repo.load_provider_history(provider_code)
        if history.empty:
            raise _not_found(f"No data for provider '{provider_code}'.")
        return TimeseriesResponse(
            scope="provider",
            provider_code=provider_code,
            label="Provider total",
            points=_history_points(history),
        )

    return TimeseriesResponse(
        scope="national",
        label="All loaded providers",
        points=_history_points(repo.load_national_trend()),
    )


def _forecast_points(row: dict[str, Any]) -> list[TimeseriesPoint]:
    """Forecast horizons rendered as chart points."""
    if row.get("forecast_status") != "ok":
        return []
    points: list[TimeseriesPoint] = []
    for horizon in (1, 3, 6):
        value = row.get(f"forecast_{horizon}m")
        month = row.get(f"forecast_{horizon}m_month")
        if value is None or not month:
            continue
        points.append(
            TimeseriesPoint(
                month_key=str(month),
                month_label=_month_label(str(month)),
                waiting_list=value,
                is_forecast=True,
                forecast_lower=row.get(f"forecast_{horizon}m_lower"),
                forecast_upper=row.get(f"forecast_{horizon}m_upper"),
            )
        )
    return points


# --- Forecast ---------------------------------------------------------------
@router.get("/forecast", response_model=ForecastResponse, tags=["forecast"])
def get_forecast(
    provider_code: str = Query(..., max_length=16),
    specialty_code: str = Query(..., max_length=16),
) -> ForecastResponse:
    """Forecast and backtest accuracy for one provider x specialty."""
    repo.require_warehouse()
    row = repo.load_forecast_row(provider_code, specialty_code)
    if not row:
        raise _not_found(
            f"No forecast record for '{provider_code}' / '{specialty_code}'."
        )
    return _forecast_response(provider_code, specialty_code, row)


# --- Scenario ---------------------------------------------------------------
@router.post("/scenario", response_model=ScenarioResponse, tags=["scenario"])
def post_scenario(request: ScenarioRequest) -> ScenarioResponse:
    """Run an illustrative activity-uplift scenario."""
    repo.require_warehouse()
    history = repo.load_service_history(request.provider_code, request.specialty_code)
    if history.empty:
        raise _not_found(
            f"No data for '{request.provider_code}' / '{request.specialty_code}'."
        )

    history = history.assign(
        provider_code=request.provider_code, specialty_code=request.specialty_code
    )
    forecast_row = repo.load_forecast_row(
        request.provider_code, request.specialty_code
    )
    service = repo.service_row(request.provider_code, request.specialty_code) or {}

    uplifts = list(request.compare_uplifts or DEFAULT_UPLIFTS)
    if request.uplift_pct not in uplifts:
        uplifts.append(request.uplift_pct)
    uplifts = sorted({float(np.clip(u, 0.0, 100.0)) for u in uplifts})

    primary = run_scenario(history, forecast_row, request.uplift_pct)
    series: list[ScenarioSeries] = []
    for uplift in uplifts:
        result = run_scenario(history, forecast_row, uplift)
        if result.status != "ok":
            continue
        series.append(
            ScenarioSeries(
                uplift_pct=uplift,
                points=[
                    {
                        "horizon_months": p.horizon_months,
                        "month_key": p.month,
                        "baseline_backlog": p.baseline_backlog,
                        "scenario_backlog": p.scenario_backlog,
                        "difference_from_baseline": p.difference_from_baseline,
                        "additional_activity_cumulative": (
                            p.additional_activity_cumulative
                        ),
                    }
                    for p in result.points
                ],
            )
        )

    return ScenarioResponse(
        provider_code=request.provider_code,
        provider_name=service.get("provider_name"),
        specialty_code=request.specialty_code,
        specialty_name=service.get("specialty_name"),
        status=primary.status,
        uplift_pct=primary.uplift_pct,
        baseline_monthly_activity=primary.baseline_monthly_activity,
        additional_monthly_activity=primary.additional_monthly_activity,
        series=series,
        uplift_required_to_stabilise_pct=primary.uplift_required_to_stabilise_pct,
        stabilisation_feasible=primary.stabilisation_feasible,
        assumptions=primary.assumptions or scenario_assumptions(),
        disclaimer=SCENARIO_DISCLAIMER,
        message=primary.message,
    )


# --- Service & provider detail ---------------------------------------------
@router.get(
    "/service/{provider_code}/{specialty_code}",
    response_model=ServiceDetailResponse,
    tags=["analytics"],
)
def get_service_detail(
    provider_code: str,
    specialty_code: str,
    scenario_uplift_pct: float = Query(10.0, ge=0.0, le=100.0),
) -> ServiceDetailResponse:
    """Everything about one provider x specialty."""
    repo.require_warehouse()
    service = repo.service_row(provider_code, specialty_code)
    if service is None:
        raise _not_found(
            f"No service found for '{provider_code}' / '{specialty_code}'."
        )

    history = repo.load_service_history(provider_code, specialty_code)
    forecast_row = repo.load_forecast_row(provider_code, specialty_code)
    forecast = _forecast_response(provider_code, specialty_code, forecast_row)

    scenario = post_scenario(
        ScenarioRequest(
            provider_code=provider_code,
            specialty_code=specialty_code,
            uplift_pct=scenario_uplift_pct,
        )
    )

    scenario_summary: dict[str, Any] = {"status": scenario.status}
    if scenario.status == "ok":
        selected = next(
            (s for s in scenario.series if s.uplift_pct == scenario_uplift_pct), None
        )
        point = (
            next((p for p in selected.points if p.horizon_months == 3), None)
            if selected
            else None
        )
        scenario_summary.update(
            {
                "uplift_pct": scenario_uplift_pct,
                "difference_from_baseline": (
                    point.difference_from_baseline if point else None
                ),
                "uplift_required_to_stabilise_pct": (
                    scenario.uplift_required_to_stabilise_pct
                ),
            }
        )

    briefing_obj = build_service_briefing(
        {**service, **forecast_row},
        provider_name=str(service.get("provider_name") or provider_code),
        specialty_name=str(service.get("specialty_name") or specialty_code),
        scenario_summary=scenario_summary,
    )
    briefing = Briefing(
        headline=briefing_obj.headline,
        priority_band=briefing_obj.priority_band,
        priority_score=briefing_obj.priority_score,
        sections=[BriefingSection(**s) for s in briefing_obj.sections],
        drivers=briefing_obj.drivers,
        recommended_actions=briefing_obj.recommended_actions,
        caveats=briefing_obj.caveats,
        generated_by=briefing_obj.generated_by,
    )

    components = [
        ScoreComponent(
            key=c.key,
            label=c.label,
            score=service.get(f"score_{c.key}"),
            contribution=service.get(f"contribution_{c.key}"),
            max_contribution=c.weight,
            description=c.description,
        )
        for c in COMPONENTS
    ]

    issues = repo.load_quality_issues()
    scoped = issues[
        (issues["provider_code"] == provider_code)
        & (issues["specialty_code"] == specialty_code)
    ]

    peer_context = {
        key: service.get(key)
        for key in service
        if key.startswith(("peer_median_", "national_median_"))
    }

    allowed = set(ServiceRow.model_fields.keys())
    return ServiceDetailResponse(
        service=ServiceRow(**{k: v for k, v in service.items() if k in allowed}),
        score_components=components,
        history=_history_points(history),
        forecast=forecast,
        scenario=scenario,
        briefing=briefing,
        quality_issues=repo.records(scoped.head(50)),
        peer_context=peer_context,
        provenance=_provenance(),
    )


@router.get(
    "/provider/{provider_code}",
    response_model=ProviderDetailResponse,
    tags=["analytics"],
)
def get_provider_detail(provider_code: str) -> ProviderDetailResponse:
    """Provider roll-up with its specialty breakdown."""
    repo.require_warehouse()
    providers = repo.load_providers()
    matched = providers[providers["provider_code"] == provider_code]
    if matched.empty:
        raise _not_found(f"No provider with code '{provider_code}'.")

    snapshot = repo.load_snapshot()
    services = snapshot[snapshot["provider_code"] == provider_code].sort_values(
        "priority_score", ascending=False
    )

    waiting = float(services["total_incomplete_pathways"].sum())
    within = float(services["within_18_weeks"].sum())
    over_52 = float(services.get("over_52_weeks", pd.Series(dtype=float)).sum())
    summary = {
        "waiting_list": waiting,
        "within_18_weeks": within,
        "pct_within_18_weeks": (within / waiting * 100.0) if waiting else None,
        "over_52_weeks": over_52,
        "pct_over_52_weeks": (over_52 / waiting * 100.0) if waiting else None,
        "specialty_count": int(len(services)),
        "high_priority_specialties": int(
            services["priority_band"].isin(["HIGH", "CRITICAL"]).sum()
        ),
        "max_priority_score": (
            float(services["priority_score"].max()) if not services.empty else None
        ),
        "provider_quality_score": (
            float(services["provider_quality_score"].iloc[0])
            if "provider_quality_score" in services.columns and not services.empty
            and pd.notna(services["provider_quality_score"].iloc[0])
            else None
        ),
    }

    return ProviderDetailResponse(
        provider=Provider(**repo.records(matched)[0]),
        summary=summary,
        services=_service_rows(services),
        history=_history_points(repo.load_provider_history(provider_code)),
        provenance=_provenance(),
    )


@router.get("/compare", response_model=ComparisonResponse, tags=["analytics"])
def get_comparison(
    specialty_code: str = Query(..., max_length=16),
    provider_codes: list[str] = Query(..., min_length=1, max_length=5),
) -> ComparisonResponse:
    """Compare up to five providers within one treatment function."""
    repo.require_warehouse()
    snapshot = repo.load_snapshot()
    codes = list(dict.fromkeys(provider_codes))[:5]

    matched = snapshot[
        (snapshot["specialty_code"] == specialty_code)
        & (snapshot["provider_code"].isin(codes))
    ].sort_values("priority_score", ascending=False)

    if matched.empty:
        raise _not_found(
            f"No data for specialty '{specialty_code}' at the selected providers."
        )

    history = {
        code: _history_points(repo.load_service_history(code, specialty_code))
        for code in codes
    }

    peer_source = snapshot[snapshot["specialty_code"] == specialty_code]
    peer_source = peer_source[peer_source.get("is_rankable", True)]
    peer_median = {}
    for column in (
        "pct_within_18_weeks", "pct_over_52_weeks", "backlog_growth_3m_pct",
        "priority_score", "total_incomplete_pathways",
    ):
        if column in peer_source.columns and not peer_source.empty:
            value = peer_source[column].median()
            peer_median[column] = (
                float(value) if pd.notna(value) else None
            )

    specialties = repo.load_specialties()
    name = specialties[specialties["specialty_code"] == specialty_code]

    return ComparisonResponse(
        specialty_code=specialty_code,
        specialty_name=(
            str(name["specialty_name"].iloc[0]) if not name.empty else None
        ),
        providers=_service_rows(matched),
        history=history,
        peer_median=peer_median,
    )


# --- Data quality -----------------------------------------------------------
_QUALITY_DIMENSIONS = {
    "completeness": (
        "Completeness",
        "Populated key measures and the rectangularity of the provider x "
        "specialty x month panel.",
    ),
    "consistency": (
        "Consistency",
        "Duplicates, negative counts, components exceeding totals, "
        "out-of-range percentages and reconciliation against published values.",
    ),
    "freshness": (
        "Freshness",
        "Age of the most recent loaded reporting period. NHS England publishes "
        "RTT roughly six to eight weeks in arrears, so a two-month lag scores "
        "full marks.",
    ),
    "anomaly_burden": (
        "Anomaly burden",
        "Share of month-on-month movements flagged as unusual by a robust "
        "z-score. Flagged movements require review; they are not assumed to be "
        "errors.",
    ),
}


@router.get("/data-quality", response_model=DataQualityResponse, tags=["quality"])
def get_data_quality(
    severity: str | None = Query(None, max_length=16),
    issue_type: str | None = Query(None, max_length=64),
    provider_code: str | None = Query(None, max_length=16),
    limit: int = Query(200, ge=1, le=2000),
) -> DataQualityResponse:
    """Data quality score, dimension breakdown and the issue register."""
    repo.require_warehouse()
    meta = repo.load_metadata()
    issues = repo.load_quality_issues()

    filtered = issues
    if severity:
        filtered = filtered[
            filtered["severity"].str.lower() == severity.strip().lower()
        ]
    if issue_type:
        filtered = filtered[filtered["issue_type"] == issue_type]
    if provider_code:
        filtered = filtered[filtered["provider_code"] == provider_code]

    # Dimension scores are recomputed from the same fact table the build used,
    # so the page and the build agree by construction. Cached per process.
    report = repo.load_quality_report()

    dimensions = [
        QualityDimension(
            key=key,
            label=_QUALITY_DIMENSIONS[key][0],
            score=report.dimension_scores[key],
            weight=QUALITY_WEIGHTS[key],
            contribution=report.dimension_contributions[key],
            description=_QUALITY_DIMENSIONS[key][1],
        )
        for key in QUALITY_WEIGHTS
    ]

    allowed = set(QualityIssueRow.model_fields.keys())
    rows = [
        QualityIssueRow(
            **{k: v for k, v in record.items() if k in allowed}
        )
        for record in repo.records(filtered.head(limit))
    ]

    return DataQualityResponse(
        overall_score=float(meta.get("quality_score") or report.overall_score),
        dimensions=dimensions,
        metrics=report.metrics,
        issues=rows,
        total_issues=int(len(issues)),
        returned_issues=len(rows),
        issue_type_counts={
            str(k): int(v) for k, v in issues["issue_type"].value_counts().items()
        }
        if not issues.empty
        else {},
        severity_counts={
            str(k): int(v) for k, v in issues["severity"].value_counts().items()
        }
        if not issues.empty
        else {},
        provenance=_provenance(),
    )


# --- Methodology ------------------------------------------------------------
@router.get("/methodology", response_model=MethodologyResponse, tags=["metadata"])
def get_methodology() -> MethodologyResponse:
    """How every number in this product is produced."""
    meta = repo.load_metadata() if repo.warehouse_available() else {}
    return MethodologyResponse(
        sections=build_methodology(meta),
        priority_components=component_metadata(),
        priority_bands=band_metadata(),
        quality_weights=QUALITY_WEIGHTS,
        forecast_summary={
            "series_ok": meta.get("forecast_series_ok"),
            "series_insufficient": meta.get("forecast_series_insufficient"),
            "median_mape": meta.get("forecast_median_mape"),
            "share_beating_naive": meta.get("forecast_share_beating_naive"),
        },
        limitations=LIMITATIONS,
        provenance=_provenance(),
    )


LIMITATIONS = [
    "Built entirely on aggregate public statistics. No patient-level data is "
    "used, held or inferred.",
    "NHS England publishes RTT data roughly six to eight weeks after month "
    "end, so the latest position always lags the operational present.",
    "The data is observational. Nothing in this product identifies a causal "
    "effect, and no intervention effect is estimated.",
    "Forecasts extrapolate recent behaviour over 12-24 monthly observations. "
    "They will not anticipate policy changes, industrial action, reporting "
    "changes or organisational restructuring.",
    "Scenario outputs are accounting projections under stated assumptions. "
    "They do not model referral response, case mix, clinical urgency or "
    "whether an activity uplift is achievable.",
    "Workforce, theatre, estate and diagnostic capacity constraints are not "
    "represented, because they are not published at this grain.",
    "The priority score is a weighted index reflecting stated judgements about "
    "what matters. Different weights produce different rankings.",
    "Published NHS England data is periodically revised. Figures here reflect "
    "the vintage retrieved at build time, recorded in the ingestion audit log.",
    "Provider organisations merge, split and re-code over time. Series spanning "
    "an organisational change may not be like-for-like.",
    "Independent-sector providers are reported separately by NHS England and "
    "are excluded from the provider sheet this product ingests.",
]
