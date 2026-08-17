"""Methodology content served to the in-app "How it works" page.

Kept as structured data rather than prose in the frontend so the explanation
lives next to the code that implements it.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.models.schemas import MethodologySection


def build_methodology(metadata: dict[str, Any]) -> list[MethodologySection]:
    """Assemble the methodology sections, filling in live build figures."""
    settings = get_settings()
    months = metadata.get("reporting_months") or "the loaded"
    latest = metadata.get("latest_reporting_month") or "the latest available"

    return [
        MethodologySection(
            key="source",
            title="1. Source data",
            body=(
                "The product ingests NHS England's monthly Consultant-led "
                "Referral to Treatment (RTT) Waiting Times statistics at "
                "provider level. Three published workbooks are used per "
                "reporting month: incomplete pathways (the waiting list), "
                "completed admitted pathways and completed non-admitted "
                "pathways. All are aggregate, published, non-patient-"
                "identifiable statistics released under the Open Government "
                "Licence."
            ),
            bullets=[
                f"{months} reporting months loaded, most recent {latest}.",
                "Provider-level basis, because the product compares provider "
                "organisations and their treatment functions.",
                "Filenames carry random suffixes and '-revised' markers, so "
                "files are discovered from the publication pages rather than "
                "constructed. Where a month has been restated, the highest "
                "revision is used.",
                "Every file is recorded in an ingestion audit table with its "
                "source URL, SHA-256 checksum, row count and processing status.",
            ],
        ),
        MethodologySection(
            key="transformation",
            title="2. Transformation",
            body=(
                "Published workbooks are parsed into a canonical star schema: "
                "dim_provider, dim_specialty, dim_date and fact_rtt at one row "
                "per provider x treatment function x reporting month. Column "
                "captions are mapped to stable canonical names in a single "
                "mapping module, so a renamed column is a one-file change."
            ),
            bullets=[
                "Suppressed and non-numeric cells ('-', '*') become null, "
                "never zero: treating suppression as zero would understate "
                "waiting lists and bias every derived metric.",
                "The 'Total' treatment function (C_999) is excluded to avoid "
                "double counting. This was verified against a published month: "
                "C_999 equals the sum of all other treatment functions.",
                "The 'Other - ...' groupings (X02-X06) are retained; they are "
                "genuine non-overlapping specialty groupings and account for "
                "roughly a third of the national list.",
                "Percentages are recomputed from counts rather than inherited "
                "from the publication, then reconciled against the published "
                "values as a data quality check.",
            ],
        ),
        MethodologySection(
            key="metrics",
            title="3. Waiting-list metrics",
            body=(
                "Longitudinal metrics are computed within each provider x "
                "specialty series ordered by reporting month. Division is "
                "NaN-safe throughout: a specialty appearing for the first time "
                "has no valid growth rate, and returning null keeps it "
                "excludable rather than letting an infinity poison every "
                "downstream percentile."
            ),
            formula=(
                "backlog_growth_3m_pct = (list_t - list_{t-3}) / list_{t-3} x 100\n"
                "pct_within_18_weeks   = within_18_weeks / total_incomplete x 100\n"
                "trend_slope_6m        = OLS slope of the last 6 monthly values\n"
                "months_to_clear       = list_t / mean(completed activity, 3m)\n"
                "implied_additions     = backlog_change_1m + completed_pathways"
            ),
            bullets=[
                "'Implied additions' is an accounting identity, not observed "
                "referrals. NHS England does not publish referrals at this "
                "grain, so the term 'demand' is deliberately avoided.",
                "Volatility is the rolling standard deviation of monthly "
                "changes, used to contextualise growth rates.",
                "Persistence counts consecutive months of deterioration and "
                "the share of the last six months in which the list grew.",
            ],
        ),
        MethodologySection(
            key="priority",
            title="4. Priority score",
            body=(
                "A transparent weighted index from 0 to 100, not a machine "
                "learning model. Every component is normalised cross-"
                "sectionally within the latest reporting month, so the score "
                "expresses relative position among peers rather than absolute "
                "severity. Each component's contribution is stored alongside "
                "the total, so any score can be decomposed."
            ),
            formula=(
                "Priority = 0.30 x Backlog growth pressure\n"
                "         + 0.25 x Long-wait burden\n"
                "         + 0.20 x 18-week performance gap\n"
                "         + 0.15 x Forecast deterioration risk\n"
                "         + 0.10 x Trend persistence\n\n"
                "Bands: 0-24 LOW | 25-49 MODERATE | 50-74 HIGH | 75-100 CRITICAL"
            ),
            bullets=[
                "Percentile rank is used where only ordering is meaningful; "
                "clipped robust scaling (5th-95th percentile) is used where "
                "magnitude carries information, such as the 18-week gap.",
                "Min-max scaling is deliberately avoided: one extreme provider "
                "would otherwise compress everyone else into the bottom of the "
                "range.",
                f"Services with fewer than "
                f"{settings.min_waiting_list_for_ranking} pathways are scored "
                "but excluded from headline rankings, because small lists "
                "produce unstable percentage growth.",
                "Components that cannot be computed score a neutral 50 rather "
                "than zero, so a missing forecast neither rewards nor punishes "
                "a service.",
                f"The 18-week gap is measured against a "
                f"{settings.referral_to_treatment_benchmark:.0f}% operational "
                "benchmark. This is applied as a comparison point, not as a "
                "claim about any organisation's contractual target.",
            ],
        ),
        MethodologySection(
            key="forecasting",
            title="5. Forecasting",
            body=(
                "Short-horizon waiting-list forecasts at +1, +3 and +6 months. "
                "Models are deliberately interpretable: with 12-24 monthly "
                "observations per series, anything elaborate would overfit, and "
                "the audience needs to be able to challenge the method in an "
                "operational meeting."
            ),
            formula=(
                "Candidates: naive drift, linear trend (full and 6-month "
                "window), Holt linear, damped trend.\n"
                "Selection : lowest one-step MAE under expanding-window "
                "rolling-origin backtesting.\n"
                "Intervals : point +/- 1.28 x sigma x sqrt(h)  (indicative 80%)"
            ),
            bullets=[
                "Every model is scored against a no-change naive benchmark, "
                "and the share of series that genuinely beat naive is "
                "published rather than hidden.",
                f"Series with fewer than {settings.min_history_for_forecast} "
                "usable observations return 'insufficient_history' rather than "
                "a fabricated forecast.",
                "Confidence labels come from backtest MAPE, not from in-sample "
                "fit: High <= 3%, Moderate <= 8%, otherwise Low.",
                "Intervals are described as indicative bands. A 95% band on "
                "these series is so wide it stops being decision-useful, so an "
                "80% band is used and labelled honestly.",
            ],
        ),
        MethodologySection(
            key="scenario",
            title="6. Scenario analysis",
            body=(
                "An accounting projection that asks what the modelled waiting "
                "list would look like if a service completed a given "
                "percentage more activity per month. It is not causal "
                "inference and cannot establish that added capacity will "
                "produce this result."
            ),
            formula=(
                "additional_activity = uplift% / 100 x mean(completed, 3m)\n"
                "scenario_backlog(h) = max(0, baseline_forecast(h)\n"
                "                              - h x additional_activity)\n\n"
                "uplift_to_stabilise = (forecast_3m - current)\n"
                "                      / (3 x mean_activity) x 100"
            ),
            bullets=[
                "A 0% uplift returns exactly the baseline forecast, by "
                "construction.",
                "Scenario backlog is floored at zero: a waiting list cannot be "
                "negative.",
                "Referral behaviour, case mix, clinical urgency and validation "
                "practice are assumed unchanged. In practice additional "
                "capacity can change all of them.",
                "The model does not assess whether an uplift is achievable "
                "given workforce, theatre or diagnostic constraints.",
            ],
        ),
        MethodologySection(
            key="quality",
            title="7. Data quality",
            body=(
                "A composite score across four dimensions, with every "
                "underlying finding listed on the Data Quality page. Findings "
                "are described as issues requiring review, never as errors in "
                "the published data - public statistics contain legitimate "
                "reporting changes and organisational mergers that an "
                "automated check cannot distinguish from a data problem."
            ),
            formula=(
                "Quality = 0.40 x Completeness\n"
                "        + 0.25 x Consistency\n"
                "        + 0.20 x Freshness\n"
                "        + 0.15 x Anomaly burden"
            ),
            bullets=[
                "Completeness blends populated key measures (60%) with the "
                "rectangularity of the provider x specialty x month panel (40%).",
                "Consistency covers duplicates, negative counts, components "
                "exceeding totals, out-of-range percentages, non-nesting "
                "long-wait bands, and reconciliation of our recomputed "
                "percentages against the published ones.",
                "Freshness scores full marks up to a two-month publication lag, "
                "then decays 15 points per further month.",
                "Anomalies are month-on-month movements beyond 3.5 robust "
                "standard deviations (median/MAD) with an absolute change of at "
                "least 50 pathways, so small lists do not generate noise.",
            ],
        ),
        MethodologySection(
            key="briefing",
            title="8. Management briefing",
            body=(
                "Executive briefings are generated deterministically from "
                "computed values. There is no language model in the default "
                "path. If a metric is missing, the corresponding sentence is "
                "omitted rather than filled with a plausible-sounding default, "
                "so the prose can never assert something the data does not "
                "support."
            ),
            bullets=[
                "Score drivers are ordered by each component's actual "
                "contribution, so the first bullet is always the largest "
                "single reason.",
                "Recommended actions are triggered by thresholds on specific "
                "metrics, each traceable to the value that fired it.",
                "An optional LLM briefing exists but is disabled unless an API "
                "key is supplied. It only rephrases already-computed facts and "
                "is clearly labelled as AI-generated when used.",
            ],
        ),
        MethodologySection(
            key="architecture",
            title="9. Pipeline and storage",
            body=(
                "extract -> validate -> clean -> standardise -> transform -> "
                "enrich -> persist -> test. Processed data is written to "
                "Parquet and loaded into a DuckDB analytical warehouse, where "
                "SQL views perform the aggregation. The API reads precomputed "
                "tables only; the expensive work (forecasting every series) "
                "happens once at build time."
            ),
            bullets=[
                "DuckDB plus Parquet gives an analytical warehouse with no "
                "server to configure, which keeps the project genuinely "
                "reproducible on a laptop.",
                "The storage layer is isolated behind a repository module, so "
                "PostgreSQL could replace DuckDB without touching the API.",
                "Aggregation happens in SQL, not in frontend JavaScript.",
            ],
        ),
    ]
