"""Generate the DEMO SYNTHETIC dataset.

This data is **not** NHS England data. It is generated from a random process so
the application can always be demonstrated - for example in an environment with
no outbound network access. Every row carries
``data_source_type = 'DEMO_SYNTHETIC'`` and the UI displays a persistent banner
whenever this dataset is loaded.

Provider names are deliberately fictional ("Northgate University Hospitals NHS
Foundation Trust") so no synthetic figure can ever be mistaken for a real
organisation's published position.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import _bootstrap  # noqa: F401

import numpy as np
import pandas as pd

from app.transformation.build import (
    build_dim_date,
    build_dim_provider,
    build_dim_specialty,
    build_fact_rtt,
)
from app.transformation.schema import DATA_SOURCE_DEMO
from app.utils.logging import configure_logging, get_logger

logger = get_logger("scripts.seed_demo")

RANDOM_SEED = 20260101

# Fictional providers. Region codes match the real NHS England coding scheme so
# the dimensional model exercises the same joins, but no real trust is named.
DEMO_PROVIDERS = [
    ("D01", "NORTHGATE UNIVERSITY HOSPITALS NHS FOUNDATION TRUST", "Y63"),
    ("D02", "RIVERMEAD HEALTHCARE NHS TRUST", "Y56"),
    ("D03", "KINGSFORD GENERAL HOSPITALS NHS FOUNDATION TRUST", "Y60"),
    ("D04", "ASHWELL VALLEY NHS FOUNDATION TRUST", "Y62"),
    ("D05", "SOUTHMOOR TEACHING HOSPITALS NHS TRUST", "Y58"),
    ("D06", "BRIDGEWATER PARK NHS FOUNDATION TRUST", "Y59"),
    ("D07", "ELMFIELD COMMUNITY HOSPITALS NHS TRUST", "Y61"),
    ("D08", "WESTBROOK UNIVERSITY NHS FOUNDATION TRUST", "Y56"),
    ("D09", "HAVERSTOCK REGIONAL NHS TRUST", "Y60"),
    ("D10", "CLAYBOURNE HEALTH NHS FOUNDATION TRUST", "Y62"),
    ("D11", "MARLOWE COAST NHS FOUNDATION TRUST", "Y58"),
    ("D12", "FENWICK HEATH NHS TRUST", "Y63"),
]

# Treatment functions use the genuine NHS England codes: the coding scheme is
# public reference data, and reusing it keeps the demo structurally faithful.
DEMO_SPECIALTIES = [
    ("C_100", "General Surgery Service", 1.00),
    ("C_101", "Urology Service", 0.85),
    ("C_110", "Trauma and Orthopaedic Service", 1.35),
    ("C_120", "Ear Nose and Throat Service", 1.10),
    ("C_130", "Ophthalmology Service", 1.25),
    ("C_140", "Oral Surgery Service", 0.70),
    ("C_320", "Cardiology Service", 0.80),
    ("C_330", "Dermatology Service", 0.75),
    ("C_400", "Neurology Service", 0.55),
    ("C_502", "Gynaecology Service", 0.90),
    ("X05", "Other - Surgical Services", 0.95),
    ("X02", "Other - Medical Services", 1.05),
]

MONTHS = 18


@dataclass
class DemoDataset:
    """The synthetic star schema."""

    fact: pd.DataFrame
    dim_provider: pd.DataFrame
    dim_specialty: pd.DataFrame
    dim_date: pd.DataFrame
    audit: pd.DataFrame


def build_demo_dataset(months: int = MONTHS) -> DemoDataset:
    """Generate a plausible but entirely synthetic RTT panel."""
    rng = np.random.default_rng(RANDOM_SEED)

    # Anchor the demo window so it looks contemporaneous without pretending to
    # be a specific published period.
    end = pd.Timestamp(datetime.now(timezone.utc).date()).replace(day=1) - pd.DateOffset(
        months=2
    )
    period = [end - pd.DateOffset(months=i) for i in range(months - 1, -1, -1)]

    rows: list[dict] = []
    for provider_code, provider_name, region in DEMO_PROVIDERS:
        provider_scale = rng.uniform(0.5, 1.8)
        for specialty_code, specialty_name, specialty_scale in DEMO_SPECIALTIES:
            base = rng.uniform(900, 6500) * provider_scale * specialty_scale
            # Monthly drift: most services grow slowly, a minority improve.
            drift = rng.normal(0.006, 0.016)
            performance = rng.uniform(0.45, 0.80)
            performance_drift = rng.normal(-0.002, 0.006)
            long_wait_share = max(0.0, rng.normal(0.012, 0.012))

            waiting = base
            for month in period:
                waiting = max(50.0, waiting * (1.0 + drift + rng.normal(0, 0.02)))
                performance = float(
                    np.clip(performance + performance_drift + rng.normal(0, 0.012),
                            0.20, 0.97)
                )
                total = float(round(waiting))
                within = float(round(total * performance))
                over_52 = float(round(total * max(0.0, long_wait_share
                                                  + rng.normal(0, 0.004))))
                over_65 = float(round(over_52 * rng.uniform(0.1, 0.5)))
                over_78 = float(round(over_65 * rng.uniform(0.0, 0.35)))
                over_104 = float(round(over_78 * rng.uniform(0.0, 0.2)))

                # Activity roughly tracks the list, with independent noise.
                activity = float(round(total * rng.uniform(0.10, 0.22)))
                admitted = float(round(activity * rng.uniform(0.25, 0.45)))
                non_admitted = float(activity - admitted)

                rows.append(
                    {
                        "region_code": region,
                        "provider_code": provider_code,
                        "provider_name": provider_name,
                        "specialty_code": specialty_code,
                        "specialty_name": specialty_name,
                        "reporting_month": month,
                        "total_incomplete_pathways": total,
                        "within_18_weeks": within,
                        "over_52_weeks": over_52,
                        "over_65_weeks": over_65,
                        "over_78_weeks": over_78,
                        "over_104_weeks": over_104,
                        "median_wait_weeks": float(
                            np.clip(rng.normal(16, 4), 3, 45)
                        ),
                        "percentile_92_wait_weeks": float(
                            np.clip(rng.normal(38, 8), 12, 90)
                        ),
                        "admitted_activity": admitted,
                        "non_admitted_activity": non_admitted,
                    }
                )

    frame = pd.DataFrame(rows)
    incomplete = frame.drop(columns=["admitted_activity", "non_admitted_activity"])
    admitted = frame[
        ["provider_code", "specialty_code", "reporting_month", "admitted_activity"]
    ].copy()
    non_admitted = frame[
        ["provider_code", "specialty_code", "reporting_month", "non_admitted_activity"]
    ].copy()

    dim_provider = build_dim_provider([frame])
    dim_specialty = build_dim_specialty([frame])
    fact = build_fact_rtt(incomplete, admitted, non_admitted, DATA_SOURCE_DEMO)
    dim_date = build_dim_date(list(fact["reporting_month"].unique()))

    audit = pd.DataFrame(
        [
            {
                "dataset": "demo",
                "reporting_period": pd.Timestamp(m).strftime("%Y-%m"),
                "source_url": "(generated)",
                "source_file": "seed_demo.py",
                "source_page": "(generated)",
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "bytes_downloaded": 0,
                "checksum_sha256": None,
                "row_count": int(
                    (fact["reporting_month"] == m).sum()
                ),
                "processing_status": "processed",
                "data_source_type": DATA_SOURCE_DEMO,
                "published_date": None,
                "source_period_label": pd.Timestamp(m).strftime("%B %Y"),
                "revision": 0,
                "message": "DEMO SYNTHETIC DATA - illustrative only.",
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
            for m in sorted(fact["reporting_month"].unique())
        ]
    )

    logger.info(
        "Generated demo dataset: %d fact rows across %d months",
        len(fact), len(dim_date),
    )
    return DemoDataset(fact, dim_provider, dim_specialty, dim_date, audit)


def main() -> int:
    configure_logging("INFO")
    from app.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    settings.ensure_directories()

    dataset = build_demo_dataset()
    target = settings.sample_dir / "demo_fact_rtt.parquet"
    dataset.fact.to_parquet(target, index=False)
    dataset.dim_provider.to_parquet(
        settings.sample_dir / "demo_dim_provider.parquet", index=False
    )
    dataset.dim_specialty.to_parquet(
        settings.sample_dir / "demo_dim_specialty.parquet", index=False
    )
    print(f"Demo dataset written to {settings.sample_dir}")
    print(f"  fact rows : {len(dataset.fact):,}")
    print(f"  providers : {len(dataset.dim_provider)}")
    print(f"  months    : {len(dataset.dim_date)}")
    print("  NOTE: DEMO SYNTHETIC DATA - illustrative only, not NHS statistics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
