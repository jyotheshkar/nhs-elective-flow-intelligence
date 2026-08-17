# Limitations

A decision-support tool that overstates its own confidence is worse than no tool. This
document states plainly what this product cannot do.

---

## 1. Data limitations

### 1.1 Aggregate only — no patient-level information

Everything here is built on published aggregate statistics. There is no patient-level
data, no case mix, no clinical urgency, no comorbidity, no cancer or urgent-pathway
flag.

**Consequence.** Two services with identical waiting lists may face entirely different
clinical risk. The priority score measures *operational pressure on the reported
position*, not clinical risk. A service ranked LOW here may still contain the patient
in most urgent need.

### 1.2 Reporting lag

NHS England publishes RTT roughly six to eight weeks after month end. In the reference
build, March 2026 data was published on 14 May 2026.

**Consequence.** The "current position" is always historical. A service that
deteriorated sharply last month will not appear here for two months. This product
supports strategic and tactical review, not real-time operational management.

### 1.3 Revisions

NHS England restates published months (`-revised`, `-revised-2` files). The ingestion
layer takes the highest available revision at build time.

**Consequence.** Rebuilding months later can produce different figures for the same
reporting period. This is why every file's URL, checksum and retrieval time is recorded
in `ingestion_audit` — the figures are reproducible *for a given vintage*, not
absolutely.

### 1.4 Organisational change

Provider organisations merge, split, and are re-coded. Treatment function codes change
between vintages.

**Consequence.** A series spanning an organisational change is **not like-for-like**. A
merger can appear as a large step-change in the waiting list and will be flagged as an
anomaly by the quality engine — correctly identifying something unusual, but not the
cause. Cross-period comparison for affected organisations should be treated with
caution.

### 1.5 Independent sector excluded

NHS England reports independent-sector providers on a separate worksheet
(`IS Provider`), which this product does not ingest.

**Consequence.** Where an NHS provider outsources significant elective activity, the
completed-activity figures here understate total throughput for those patients. The
scenario model's activity baseline is correspondingly conservative.

### 1.6 Small-number suppression

Suppressed values (`*`) become null, never zero.

**Consequence.** Small services may have incomplete long-wait bands, so their long-wait
burden component may be computed on partial information. They are largely excluded from
rankings by the 200-pathway threshold, which mitigates but does not eliminate this.

### 1.7 No referral data at this grain

NHS England does not publish referrals at provider × specialty × month.

**Consequence.** `implied_additions` is an accounting residual, not observed demand. It
absorbs referrals, validation removals, transfers between providers and reporting
changes into a single figure. The product therefore never uses the word "demand" and
labels this measure as *implied*.

---

## 2. Analytical limitations

### 2.1 Observational data — no causal claims

Nothing in this product identifies a causal effect. There is no randomisation, no
instrument, no natural experiment, no counterfactual.

**Consequence.** Correlations between activity and backlog reflect whatever process
generated both. The scenario engine is explicitly an arithmetic projection, not an
estimate of what would happen if capacity were added.

### 2.2 The priority score encodes judgement

The weights (30/25/20/15/10) are a stated judgement about what matters operationally,
not a validated instrument. They have not been calibrated against any outcome, because
no suitable outcome measure exists in the public data.

**Consequence.** Different weights produce different rankings. A reviewer who believes
long waits should outweigh growth would reorder the top of the list. This is why the
weights are published in-app and every score is fully decomposable — the framework is
arguable *by design*.

### 2.3 Relative, not absolute

Components are normalised cross-sectionally within the latest month.

**Consequence.** A score of 85 means "high pressure **relative to peers this month**",
not "high pressure in absolute terms". In a month where every service improved, some
service would still score 90+. Scores are **not comparable across builds** with
different reporting months.

### 2.4 Small services are not scored at all

Services under 200 pathways are excluded from the scoring basis and reported as
`UNSCORED`.

**Consequence.** A small specialty deteriorating rapidly receives **no priority score**
and will not appear in rankings. Its published metrics — list size, growth, 18-week
position, long waits — are shown in full, and it is reachable by filtering, but the
prioritisation framework simply does not cover it.

This is a deliberate trade-off. Percentage growth on a 40-pathway list is
noise-dominated, and because the score is a cross-sectional statistic, a service outside
the basis would receive the neutral fallback on every component and total exactly 50 —
appearing as "HIGH" purely as an artefact of the defaults. Withholding the score is more
honest than publishing a meaningless one, but it does mean roughly 1,400 of 3,450
services carry no prioritisation signal.

### 2.5 Missing components score neutrally

A component that cannot be computed scores 50.

**Consequence.** A service with no forecast gets a mid-range score on 15% of the index,
regardless of its actual trajectory. This is the least-bad option — zero would reward
missing data, 100 would punish it — but it does compress scores toward the middle for
data-sparse services.

---

## 3. Forecasting limitations

### 3.1 Short series

12–24 monthly observations per series. That is very little data.

**Consequence.** Only simple models are defensible. Parameter estimates are imprecise.
Prediction intervals are indicative, not rigorous — which is why an 80% band is used and
labelled as such, rather than a 95% band that would imply more precision than exists.

### 3.2 Extrapolation of recent behaviour only

The models project forward whatever the series has recently been doing.

**Consequence.** They will not anticipate: policy or target changes, industrial action,
funding decisions, seasonal capacity changes not present in the loaded window, reporting
or coding changes, organisational restructuring, or pandemic-scale disruption. A forecast
is a statement about *continuation of recent behaviour*, nothing more.

### 3.3 Naive often wins

On the reference build only **56.1%** of series beat a no-change benchmark, and
`naive_drift` was selected for 43% of them.

**Consequence.** For a large minority of services these forecasts add little over "next
month looks like this month". This is reported in the product rather than hidden,
because the alternative — presenting all forecasts as equally informative — would be
misleading. The confidence label exists to make this legible per service.

### 3.4 No seasonality modelling

18 months is barely one and a half annual cycles — not enough to identify a seasonal
component without overfitting.

**Consequence.** Genuine seasonal effects (winter pressures, summer annual leave) are
absorbed into the trend and residual, which inflates apparent uncertainty and may bias
short-horizon forecasts made at a seasonal turning point.

### 3.5 Series are modelled independently

Each provider × specialty is forecast in isolation.

**Consequence.** No pooling, no hierarchical structure, no cross-series information
sharing. A specialty-wide shock is not propagated. Summing individual forecasts (as the
"Forecast list (3 months)" KPI does) ignores correlation between series, so the
aggregate uncertainty is understated.

---

## 4. Scenario limitations

### 4.1 Accounting, not behaviour

The model subtracts additional completed activity from the projected backlog.

**Consequence.** It assumes one-for-one removal with no behavioural response. In
practice, increased capacity can increase referrals (supply-induced demand), change case
mix toward more complex patients, and alter validation practice. None of that is
modelled.

### 4.2 Achievability is not assessed

The model will happily compute a 20% uplift scenario for a service with no theatre
capacity, no available workforce and no diagnostic slots.

**Consequence.** "The uplift required to stabilise is 11.4%" is an arithmetic statement,
not an operational recommendation. Whether 11.4% is trivially achievable or completely
impossible is outside what public data can answer.

### 4.3 Baseline inherits forecast uncertainty

The scenario is applied to the forecast, so all forecast limitations flow through.

**Consequence.** The *difference* between scenarios is more robust than the absolute
level, because both share the same baseline error. Reading "10% uplift is ~146 pathways
better than baseline over 3 months" is safer than reading the projected backlog as a
prediction.

### 4.4 Uniform activity assumption

The uplift is applied uniformly to the 3-month mean activity.

**Consequence.** It does not model ramp-up time, capacity sustainability, or the fact
that the marginal patient treated is typically harder to schedule than the average one.

---

## 5. Data quality engine limitations

### 5.1 Anomalies are not errors

Flagged month-on-month movements may be genuine operational change, a reporting change,
an organisational merger, or a data problem. An automated check cannot distinguish
these.

**Consequence.** The 1,011 anomalies flagged on the reference build are *items requiring
review*, not 1,011 data errors. Every description says so explicitly.

### 5.2 Only internally-checkable properties are checked

The engine verifies internal consistency (parts ≤ wholes, bands nest, percentages in
range, our derivations reconcile with published ones).

**Consequence.** It cannot detect a systematically wrong but internally consistent
submission. If a provider under-reports its waiting list uniformly, nothing here would
notice.

### 5.3 The quality weights are a judgement

40/25/20/15 is a stated opinion, not a standard.

**Consequence.** The composite score is useful for tracking change over time and
comparing providers on the same basis, not as an absolute measure of data fitness.

---

## 6. Product scope limitations

Deliberately **not** built, because they would add complexity without portfolio signal
or would misrepresent what public data supports:

- Authentication, user accounts, role-based access
- Patient-level anything: booking, triage, tracking, clinical decision support
- Real-time or streaming data (the source is monthly)
- Workforce, financial or theatre-utilisation modelling (not published at this grain)
- Diagnostic waiting times (DM01) — genuinely valuable, listed as a future improvement
- Cross-provider patient flow (not published)
- Cancer or urgent-pathway breakdowns (a separate collection with different structure)

---

## 7. Technical limitations

- **Single-node.** DuckDB in-process. Appropriate for ~63k rows; would need
  reconsideration at a much larger scale.
- **No incremental ingestion.** A rebuild re-processes the full window. Fine at this
  size (~4 minutes offline), but not how a production pipeline would be structured.
- **Process-lifetime caching.** Cached frames refresh only on restart. A warehouse
  rebuilt while the API is running is not picked up until the API restarts.
- **No historical vintages retained.** Only the latest revision is stored, so the
  product cannot currently show how a month's position was restated over time.

---

## 8. What this product is not

- Not a clinical decision support system
- Not a patient triage or prioritisation tool
- Not a diagnosis application
- Not a patient-level system
- Not a replacement for NHS operational judgement
- Not deployed in, used by, or endorsed by any NHS organisation
- Not an official source of NHS statistics

Priority scores, forecasts and scenario outputs are **derived measures produced by this
application**. They are not NHS England statistics and must not be presented as such.

For the authoritative published position, always refer to
[NHS England's RTT publication](https://www.england.nhs.uk/statistics/statistical-work-areas/rtt-waiting-times/).
