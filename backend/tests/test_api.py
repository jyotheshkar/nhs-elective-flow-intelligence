"""API contract tests.

These run against the real built warehouse when one exists, and otherwise
verify the degraded-mode behaviour (which is itself a requirement: the API must
return an actionable 503 rather than crashing when no data has been ingested).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.database import warehouse
from app.main import app

WAREHOUSE_AVAILABLE = warehouse.warehouse_exists()

needs_warehouse = pytest.mark.skipif(
    not WAREHOUSE_AVAILABLE,
    reason="No warehouse built; run 'make data' or 'make demo' first.",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


class TestServiceEndpoints:
    def test_health_always_responds(self, client: TestClient):
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"ok", "degraded"}
        assert body["warehouse_available"] == WAREHOUSE_AVAILABLE

    def test_root_carries_the_disclaimer(self, client: TestClient):
        body = client.get("/").json()
        assert "not affiliated with or endorsed by nhs england" in (
            body["disclaimer"].lower()
        )

    def test_openapi_loads(self, client: TestClient):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "NHS Elective Flow Intelligence"
        assert "/api/v1/overview" in schema["paths"]
        assert "/api/v1/scenario" in schema["paths"]

    def test_metadata_always_responds(self, client: TestClient):
        response = client.get("/api/v1/metadata")
        assert response.status_code == 200
        body = response.json()
        assert "provenance" in body
        assert body["provenance"]["data_source_type"]


@pytest.mark.skipif(
    WAREHOUSE_AVAILABLE, reason="Warehouse exists; degraded mode not applicable."
)
class TestDegradedMode:
    def test_analytics_returns_actionable_503(self, client: TestClient):
        response = client.get("/api/v1/overview")
        assert response.status_code == 503
        body = response.json()
        assert "remedy" in body
        assert any("make data" in r for r in body["remedy"])


@needs_warehouse
class TestReferenceEndpoints:
    def test_providers(self, client: TestClient):
        rows = client.get("/api/v1/providers").json()
        assert len(rows) > 0
        assert {"provider_code", "provider_name"} <= set(rows[0])

    def test_specialties(self, client: TestClient):
        rows = client.get("/api/v1/specialties").json()
        assert len(rows) > 0
        assert {"specialty_code", "specialty_name"} <= set(rows[0])

    def test_regions(self, client: TestClient):
        rows = client.get("/api/v1/regions").json()
        assert len(rows) > 0

    def test_reporting_periods_newest_first(self, client: TestClient):
        rows = client.get("/api/v1/reporting-periods").json()
        assert len(rows) > 0
        assert rows[0]["is_latest"] is True
        keys = [r["month_key"] for r in rows]
        assert keys == sorted(keys, reverse=True)


@needs_warehouse
class TestOverview:
    def test_returns_expected_shape(self, client: TestClient):
        body = client.get("/api/v1/overview").json()
        for key in ("kpis", "attention", "matrix", "national_trend",
                    "band_counts", "provenance"):
            assert key in body
        assert len(body["kpis"]) == 6

    def test_kpis_carry_their_definitions(self, client: TestClient):
        body = client.get("/api/v1/overview").json()
        for kpi in body["kpis"]:
            assert kpi["definition"]
            assert kpi["source"]
            assert kpi["calculation"]

    def test_filters_reduce_the_result(self, client: TestClient):
        unfiltered = client.get("/api/v1/overview").json()
        specialty = client.get(
            "/api/v1/overview", params={"specialty_code": "C_110"}
        ).json()
        assert specialty["filters_applied"]["specialty_code"] == "C_110"
        assert sum(specialty["band_counts"].values()) <= sum(
            unfiltered["band_counts"].values()
        )

    def test_unknown_filter_returns_empty_not_error(self, client: TestClient):
        response = client.get(
            "/api/v1/overview", params={"provider_code": "ZZZNOTREAL"}
        )
        assert response.status_code == 200
        assert response.json()["kpis"] == []

    def test_trend_scope_is_declared(self, client: TestClient):
        """The chart must never present the national series as a filtered one."""
        unfiltered = client.get("/api/v1/overview").json()
        assert unfiltered["trend_scope"] == "national"

        narrow = client.get(
            "/api/v1/overview", params={"specialty_code": "C_150"}
        ).json()
        assert narrow["trend_scope"] in {"filtered", "national"}

        # A single provider is always narrow enough to aggregate directly.
        provider = client.get("/api/v1/providers").json()[0]["provider_code"]
        single = client.get(
            "/api/v1/overview", params={"provider_code": provider}
        ).json()
        assert single["trend_scope"] == "filtered"


@needs_warehouse
class TestRankings:
    def test_default_page(self, client: TestClient):
        body = client.get("/api/v1/rankings", params={"limit": 10}).json()
        assert body["returned"] <= 10
        assert body["total"] >= body["returned"]

    def test_sorted_by_priority_descending(self, client: TestClient):
        rows = client.get("/api/v1/rankings", params={"limit": 25}).json()["rows"]
        scores = [r["priority_score"] for r in rows]
        assert scores == sorted(scores, reverse=True)

    def test_ascending_sort(self, client: TestClient):
        rows = client.get(
            "/api/v1/rankings", params={"limit": 10, "descending": False}
        ).json()["rows"]
        scores = [r["priority_score"] for r in rows]
        assert scores == sorted(scores)

    def test_alternate_sort_column(self, client: TestClient):
        rows = client.get(
            "/api/v1/rankings",
            params={"limit": 10, "sort_by": "total_incomplete_pathways"},
        ).json()["rows"]
        values = [r["total_incomplete_pathways"] for r in rows]
        assert values == sorted(values, reverse=True)

    def test_invalid_sort_column_is_rejected(self, client: TestClient):
        response = client.get(
            "/api/v1/rankings", params={"sort_by": "; DROP TABLE fact_rtt"}
        )
        assert response.status_code == 422

    def test_pagination_does_not_overlap(self, client: TestClient):
        first = client.get(
            "/api/v1/rankings", params={"limit": 10, "offset": 0}
        ).json()["rows"]
        second = client.get(
            "/api/v1/rankings", params={"limit": 10, "offset": 10}
        ).json()["rows"]
        keys = {(r["provider_code"], r["specialty_code"]) for r in first}
        assert not keys & {
            (r["provider_code"], r["specialty_code"]) for r in second
        }

    def test_limit_is_bounded(self, client: TestClient):
        assert client.get("/api/v1/rankings", params={"limit": 10_000}).status_code == 422

    def test_csv_export(self, client: TestClient):
        response = client.get("/api/v1/rankings/export", params={"limit": 5})
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        text = response.text
        # Provenance header must travel with the data.
        assert "# Data source type:" in text
        assert "provider_code" in text
        assert "derived measures produced" in text


@needs_warehouse
class TestServiceDetail:
    @pytest.fixture(scope="class")
    def top_service(self, client: TestClient) -> dict:
        return client.get("/api/v1/rankings", params={"limit": 1}).json()["rows"][0]

    def test_returns_full_payload(self, client: TestClient, top_service):
        response = client.get(
            f"/api/v1/service/{top_service['provider_code']}"
            f"/{top_service['specialty_code']}"
        )
        assert response.status_code == 200
        body = response.json()
        for key in ("service", "score_components", "history", "forecast",
                    "scenario", "briefing", "provenance"):
            assert key in body

    def test_score_components_sum_to_total(self, client: TestClient, top_service):
        body = client.get(
            f"/api/v1/service/{top_service['provider_code']}"
            f"/{top_service['specialty_code']}"
        ).json()
        total = sum(c["contribution"] or 0 for c in body["score_components"])
        assert total == pytest.approx(body["service"]["priority_score"], abs=0.2)

    def test_briefing_is_deterministic(self, client: TestClient, top_service):
        body = client.get(
            f"/api/v1/service/{top_service['provider_code']}"
            f"/{top_service['specialty_code']}"
        ).json()
        assert body["briefing"]["generated_by"] == "deterministic_rules"
        assert len(body["briefing"]["caveats"]) > 0

    def test_unknown_service_returns_404(self, client: TestClient):
        response = client.get("/api/v1/service/ZZZ/NOPE")
        assert response.status_code == 404


@needs_warehouse
class TestForecastEndpoint:
    def test_returns_forecast(self, client: TestClient):
        top = client.get("/api/v1/rankings", params={"limit": 1}).json()["rows"][0]
        body = client.get(
            "/api/v1/forecast",
            params={
                "provider_code": top["provider_code"],
                "specialty_code": top["specialty_code"],
            },
        ).json()
        assert body["status"] in {"ok", "insufficient_history"}
        assert body["method_note"]
        if body["status"] == "ok":
            assert len(body["points"]) == 3
            assert body["confidence"] in {"High", "Moderate", "Low"}

    def test_unknown_series_returns_404(self, client: TestClient):
        response = client.get(
            "/api/v1/forecast",
            params={"provider_code": "ZZZ", "specialty_code": "NOPE"},
        )
        assert response.status_code == 404


@needs_warehouse
class TestScenarioEndpoint:
    @pytest.fixture(scope="class")
    def target(self, client: TestClient) -> dict:
        rows = client.get("/api/v1/rankings", params={"limit": 20}).json()["rows"]
        return rows[0]

    def test_zero_uplift_equals_baseline(self, client: TestClient, target):
        body = client.post(
            "/api/v1/scenario",
            json={
                "provider_code": target["provider_code"],
                "specialty_code": target["specialty_code"],
                "uplift_pct": 0,
            },
        ).json()
        if body["status"] != "ok":
            pytest.skip("Scenario unavailable for this service.")
        zero = next(s for s in body["series"] if s["uplift_pct"] == 0)
        for point in zero["points"]:
            assert point["scenario_backlog"] == point["baseline_backlog"]

    def test_higher_uplift_never_increases_backlog(self, client: TestClient, target):
        body = client.post(
            "/api/v1/scenario",
            json={
                "provider_code": target["provider_code"],
                "specialty_code": target["specialty_code"],
                "uplift_pct": 10,
            },
        ).json()
        if body["status"] != "ok":
            pytest.skip("Scenario unavailable for this service.")
        by_horizon: dict[int, list[float]] = {}
        for series in sorted(body["series"], key=lambda s: s["uplift_pct"]):
            for point in series["points"]:
                by_horizon.setdefault(point["horizon_months"], []).append(
                    point["scenario_backlog"]
                )
        for values in by_horizon.values():
            assert values == sorted(values, reverse=True)

    def test_carries_disclaimer_and_assumptions(self, client: TestClient, target):
        body = client.post(
            "/api/v1/scenario",
            json={
                "provider_code": target["provider_code"],
                "specialty_code": target["specialty_code"],
                "uplift_pct": 10,
            },
        ).json()
        assert "not a causal prediction" in body["disclaimer"].lower()
        assert len(body["assumptions"]) >= 5

    def test_rejects_out_of_range_uplift(self, client: TestClient, target):
        response = client.post(
            "/api/v1/scenario",
            json={
                "provider_code": target["provider_code"],
                "specialty_code": target["specialty_code"],
                "uplift_pct": 5000,
            },
        )
        assert response.status_code == 422

    def test_rejects_unknown_fields(self, client: TestClient, target):
        response = client.post(
            "/api/v1/scenario",
            json={
                "provider_code": target["provider_code"],
                "specialty_code": target["specialty_code"],
                "uplift_pct": 10,
                "injected": "value",
            },
        )
        assert response.status_code == 422

    def test_unknown_service_returns_404(self, client: TestClient):
        response = client.post(
            "/api/v1/scenario",
            json={
                "provider_code": "ZZZ",
                "specialty_code": "NOPE",
                "uplift_pct": 10,
            },
        )
        assert response.status_code == 404


@needs_warehouse
class TestDataQuality:
    def test_returns_dimensions_and_issues(self, client: TestClient):
        body = client.get("/api/v1/data-quality", params={"limit": 20}).json()
        assert 0 <= body["overall_score"] <= 100
        assert len(body["dimensions"]) == 4
        assert sum(d["weight"] for d in body["dimensions"]) == pytest.approx(100.0)

    def test_severity_filter(self, client: TestClient):
        body = client.get(
            "/api/v1/data-quality", params={"severity": "High", "limit": 50}
        ).json()
        assert all(i["severity"] == "High" for i in body["issues"])


@needs_warehouse
class TestMethodologyAndCompare:
    def test_methodology_is_complete(self, client: TestClient):
        body = client.get("/api/v1/methodology").json()
        assert len(body["sections"]) >= 8
        assert len(body["priority_components"]) == 5
        assert sum(c["weight"] for c in body["priority_components"]) == 100
        assert len(body["limitations"]) >= 8

    def test_limitations_are_candid(self, client: TestClient):
        text = " ".join(client.get("/api/v1/methodology").json()["limitations"]).lower()
        assert "causal" in text
        assert "aggregate public statistics" in text
        assert "revised" in text

    def test_compare_up_to_five_providers(self, client: TestClient):
        providers = client.get("/api/v1/providers").json()[:3]
        codes = [p["provider_code"] for p in providers]
        response = client.get(
            "/api/v1/compare",
            params={"specialty_code": "C_110", "provider_codes": codes},
        )
        if response.status_code == 404:
            pytest.skip("Specialty not reported by the sampled providers.")
        body = response.json()
        assert len(body["providers"]) <= 5
        assert "peer_median" in body

    def test_compare_rejects_too_many_providers(self, client: TestClient):
        codes = [p["provider_code"] for p in client.get("/api/v1/providers").json()[:6]]
        response = client.get(
            "/api/v1/compare",
            params={"specialty_code": "C_110", "provider_codes": codes},
        )
        assert response.status_code == 422


@needs_warehouse
class TestProvenanceExposure:
    """Provenance is a product requirement, not decoration."""

    @pytest.mark.parametrize(
        "path",
        ["/api/v1/overview", "/api/v1/methodology", "/api/v1/data-quality"],
    )
    def test_endpoints_expose_provenance(self, client: TestClient, path: str):
        provenance = client.get(path).json()["provenance"]
        assert provenance["data_source_type"] in {
            "OFFICIAL_NHS_PUBLIC", "DEMO_SYNTHETIC"
        }
        assert provenance["reporting_months"] > 0

    def test_demo_data_is_labelled(self, client: TestClient):
        provenance = client.get("/api/v1/metadata").json()["provenance"]
        if provenance["data_source_type"] == "DEMO_SYNTHETIC":
            assert provenance["is_demo"] is True
            assert "not nhs england data" in provenance["source_name"].lower()
        else:
            assert provenance["is_demo"] is False
