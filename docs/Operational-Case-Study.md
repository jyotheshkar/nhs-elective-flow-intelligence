# Elective flow: from public data to an investigation

Independent portfolio prototype. No NHS affiliation, deployment, clinical triage or patient-outcome claim.

## Business question
Which provider x treatment-function services should an operational analyst investigate first, and what evidence explains their relative priority?

## Five-minute demonstration
1. Establish the data boundary: published aggregate RTT pathways, not unique patients; the checked reference snapshot covers October 2024 to June 2026, 155 providers, 23 specialties and 72,956 fact rows. Show reporting period and source provenance before any KPI.
2. Open rankings. Explain that priority is a relative operational index with judgement-based weights, not clinical urgency or a causal measure. Compare a deteriorating service with a stable comparator; explain the five contributions.
3. Open the forecast. Identify history, selected model, one-step rolling-origin backtest error and indicative bands. Naive drift was selected for 901/2,078 forecastable series; it is not the no-change baseline. Model selection and reported backtest use the same folds, so these are model-selection diagnostics, not independent held-out validation.
4. Change activity uplift from zero to 10 percent. Show zero uplift exactly matches baseline and higher activity cannot increase the modelled backlog. Describe it as accounting projection: capacity feasibility, case mix, referrals and clinical urgency are not modelled.
5. Open quality findings and provenance. Describe an unusual movement as a review item rather than an error in NHS data. Explain how the AWS design retains the approved release when a new candidate fails.

## Computed reference results
The loaded June 2026 dataset contains 6,693,433 incomplete pathways and 4,359,731 within 18 weeks: the weighted share is 65.13445%. These are sums over loaded data, not a separately reconciled national headline. There are zero missing numerator/denominator pairs for this month. Of 3,565 historical series, 2,078 have forecasts; median model-selection backtest MAPE is 3.6821%, and 54.7642% beat the no-change comparator on the recorded selection folds. Missing-history series remain explicitly unforecast.

## Recommendation and limitations
Use the ranking to choose questions for service teams, then validate definitions, revisions, reporting changes and operational context before recommending action. A score does not establish why deterioration happened. The next useful evaluation would hold out future months and assess 1/3/6-month errors and interval coverage separately from model selection.

Technical evidence: qa/results/warehouse-evidence.json. BI reconciliation: regenerate scripts/export_bi.py. Production-readiness remains unproven until Docker/AWS deployment, IAM checks, notification delivery and rollback drills are executed.
