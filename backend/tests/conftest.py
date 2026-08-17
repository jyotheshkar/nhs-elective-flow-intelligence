"""Shared pytest fixtures.

Tests run against a small synthetic panel rather than the real warehouse, so
they are fast, deterministic and do not require ingestion to have been run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.transformation.build import build_dim_date, build_fact_rtt
from app.transformation.schema import DATA_SOURCE_DEMO


def _panel(
    # 10 x 4 = 40 series, deliberately above the 30-series floor at which
    # priority scoring falls back to the full population. This keeps the
    # fixture exercising the normal rankable-basis path.
    providers: int = 10,
    specialties: int = 4,
    months: int = 18,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a deterministic synthetic RTT panel."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-10-01")
    rows = []

    for p in range(providers):
        for s in range(specialties):
            base = float(rng.integers(600, 9000))
            drift = float(rng.normal(0.01, 0.02))
            performance = float(rng.uniform(0.4, 0.85))
            waiting = base
            for m in range(months):
                waiting = max(60.0, waiting * (1 + drift))
                total = float(round(waiting))
                within = float(round(total * performance))
                over_52 = float(round(total * 0.02))
                rows.append(
                    {
                        "region_code": f"Y5{p % 3}",
                        "provider_code": f"P{p:02d}",
                        "provider_name": f"TEST PROVIDER {p} NHS TRUST",
                        "specialty_code": f"C_{100 + s * 10}",
                        "specialty_name": f"Test Specialty {s} Service",
                        "reporting_month": start + pd.DateOffset(months=m),
                        "total_incomplete_pathways": total,
                        "within_18_weeks": within,
                        "over_52_weeks": over_52,
                        "over_65_weeks": float(round(over_52 * 0.3)),
                        "over_78_weeks": float(round(over_52 * 0.1)),
                        "over_104_weeks": 0.0,
                        "median_wait_weeks": float(rng.uniform(8, 30)),
                        "percentile_92_wait_weeks": float(rng.uniform(25, 60)),
                        "admitted_activity": float(round(total * 0.06)),
                        "non_admitted_activity": float(round(total * 0.10)),
                    }
                )
    return pd.DataFrame(rows)


@pytest.fixture(scope="session")
def raw_panel() -> pd.DataFrame:
    """Raw synthetic panel before fact assembly."""
    return _panel()


@pytest.fixture(scope="session")
def fact(raw_panel: pd.DataFrame) -> pd.DataFrame:
    """Canonical fact table built from the synthetic panel."""
    incomplete = raw_panel.drop(
        columns=["admitted_activity", "non_admitted_activity"]
    )
    admitted = raw_panel[
        ["provider_code", "specialty_code", "reporting_month", "admitted_activity"]
    ].copy()
    non_admitted = raw_panel[
        [
            "provider_code", "specialty_code", "reporting_month",
            "non_admitted_activity",
        ]
    ].copy()
    return build_fact_rtt(incomplete, admitted, non_admitted, DATA_SOURCE_DEMO)


@pytest.fixture(scope="session")
def metrics(fact: pd.DataFrame) -> pd.DataFrame:
    """Fact table with longitudinal metrics derived."""
    from app.analytics.metrics import add_trend_metrics

    return add_trend_metrics(fact)


@pytest.fixture(scope="session")
def dim_date(fact: pd.DataFrame) -> pd.DataFrame:
    return build_dim_date(list(fact["reporting_month"].unique()))


@pytest.fixture(scope="session")
def dim_provider(raw_panel: pd.DataFrame) -> pd.DataFrame:
    from app.transformation.build import build_dim_provider

    return build_dim_provider([raw_panel])


@pytest.fixture(scope="session")
def dim_specialty(raw_panel: pd.DataFrame) -> pd.DataFrame:
    from app.transformation.build import build_dim_specialty

    return build_dim_specialty([raw_panel])


@pytest.fixture(scope="session")
def scored(metrics: pd.DataFrame) -> pd.DataFrame:
    """Latest-month snapshot with forecasts joined and priority scored."""
    from app.analytics.metrics import latest_snapshot
    from app.analytics.priority import score_snapshot
    from app.forecasting.engine import forecast_all

    forecasts = forecast_all(metrics)
    snapshot = latest_snapshot(metrics).merge(
        forecasts, on=["provider_code", "specialty_code"], how="left"
    )
    return score_snapshot(snapshot)


@pytest.fixture(scope="session")
def forecasts(metrics: pd.DataFrame) -> pd.DataFrame:
    from app.forecasting.engine import forecast_all

    return forecast_all(metrics)
