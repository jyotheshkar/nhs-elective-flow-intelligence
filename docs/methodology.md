# Methodology

Every number this product displays is traceable to a published NHS England statistic or
to a formula on this page. This document contains enough mathematics to defend the
implementation in a technical interview.

---

## 1. Source and ingestion

### 1.1 What is ingested

NHS England's **Consultant-led Referral to Treatment (RTT) Waiting Times**, provider
level. Three workbooks per reporting month:

| Dataset | Published measure used | Canonical name |
|---|---|---|
| Incomplete Provider | Total number of incomplete pathways | `total_incomplete_pathways` |
| Incomplete Provider | Total within 18 weeks | `within_18_weeks` |
| Incomplete Provider | Total 52 / 65 / 78 plus weeks | `over_52_weeks`, `over_65_weeks`, `over_78_weeks` |
| Incomplete Provider | `104 plus` weekly band | `over_104_weeks` |
| Incomplete Provider | Average (median) waiting time | `median_wait_weeks` |
| Incomplete Provider | 92nd percentile waiting time | `percentile_92_wait_weeks` |
| Admitted Provider | Total completed pathways (all) | `admitted_activity` |
| NonAdmitted Provider | Total completed pathways (all) | `non_admitted_activity` |

`completed_pathways = admitted_activity + non_admitted_activity`, summed with
`min_count=1` so a row where both components are missing stays null rather than
collapsing to zero.

### 1.2 Discovery, not construction

Published filenames carry random suffixes and revision markers:

```
Incomplete-Provider-Dec25-XLSX-9M-6jPlxd.xlsx
Incomplete-Provider-Sep25-XLSX-9M-revised.xlsx
Admitted-Provider-Aug25-XLSX-4M-revised-2.xlsx
```

They cannot be constructed, so they are discovered: publication pages are scraped, links
matched against configured patterns, the reporting month parsed from the `MonYY`
fragment, and revisions resolved by taking the **highest revision number** per
(dataset, month).

### 1.3 Suppression handling

NHS England uses `-` and `*` for suppressed or unavailable values. These become **null,
never zero**. Treating a suppressed value as zero would understate waiting lists and
bias every derived metric downstream — a service with suppressed long-wait counts would
appear to have none.

### 1.4 Aggregate exclusion

`C_999` ("Total") is dropped. **Verified, not assumed:** for provider R1H in December
2025, `C_999` = 132,390 = the exact sum of all other treatment functions (including
`X02`–`X06`).

`X02`–`X06` ("Other – Medical / Mental Health / Paediatric / Surgical / Other Services")
are **retained**: they are genuine non-overlapping groupings, and for R1H they account
for 43,839 of 132,390 pathways (33%). Excluding them would understate the national
position by roughly a third.

---

## 2. Derived metrics

All computed **within** a provider × specialty series ordered by reporting month.

### 2.1 Safe division

Every ratio uses:

$$
\text{safe\_divide}(a, b) =
\begin{cases}
a / b & \text{if } b \neq 0 \text{ and } a/b \text{ finite} \\
\text{NaN} & \text{otherwise}
\end{cases}
$$

**Why this matters.** A specialty appearing for the first time has a previous-month
value of 0. Naive division yields `inf`, which then propagates into percentile ranks and
corrupts every score in that month. Returning NaN keeps the row excludable.

### 2.2 Growth and change

$$
\text{backlog\_change\_1m}_t = L_t - L_{t-1}
$$

$$
\text{backlog\_growth\_}k\text{m\_pct}_t = \frac{L_t - L_{t-k}}{L_{t-k}} \times 100
\qquad k \in \{1, 3, 6\}
$$

where $L_t$ is `total_incomplete_pathways` at month $t$.

### 2.3 Performance ratios

$$
\text{pct\_within\_18\_weeks} = \frac{\text{within\_18\_weeks}}{L_t} \times 100
$$

$$
\text{pct\_over\_}b\text{\_weeks} = \frac{\text{over\_}b\text{\_weeks}}{L_t} \times 100
\qquad b \in \{18, 52, 65, 78, 104\}
$$

Recomputed from counts rather than inherited from the publication, so the definition is
ours and testable. The published percentages are retained and **reconciled** against the
recomputed values as a data quality check (tolerance 0.5 pp).

### 2.4 Rolling statistics

$$
\text{rolling\_3m}_t = \frac{1}{3}\sum_{i=0}^{2} L_{t-i}
\qquad (\text{min\_periods} = 2)
$$

$$
\text{volatility}_t = \operatorname{sd}\big(\{\Delta L_{t-5}, \ldots, \Delta L_t\}\big)
\qquad (\text{min\_periods} = 3)
$$

### 2.5 Trend slope

Ordinary least squares of $L$ against a time index over a trailing window of $n$ months:

$$
\hat{\beta} = \frac{\sum_{i=1}^{n}(x_i - \bar{x})(L_i - \bar{L})}{\sum_{i=1}^{n}(x_i - \bar{x})^2}
\qquad x_i = 0, 1, \ldots, n-1
$$

Units are **pathways per month**. Because absolute slope is not comparable across
services of different size, the scoring layer uses:

$$
\text{trend\_slope\_6m\_pct\_of\_list} = \frac{\hat{\beta}_{6}}{L_t} \times 100
$$

A rise of 200 pathways/month means something very different for a 500-pathway list than
for a 50,000-pathway one.

### 2.6 Persistence

$$
\text{months\_backlog\_rising}_t = \max\{ r : \Delta L_{t-j} > 0 \ \ \forall j \in [0, r) \}
$$

$$
\text{share\_months\_rising\_6m}_t = \frac{1}{6}\sum_{i=0}^{5} \mathbb{1}[\Delta L_{t-i} > 0] \times 100
$$

The run resets on any fall **and on any missing month**, so a data gap cannot manufacture
a long run.

### 2.7 Activity and implied flow

$$
\text{months\_to\_clear}_t = \frac{L_t}{\overline{A}_{3m}}
$$

where $\overline{A}_{3m}$ is mean completed pathways over the last three months.

$$
\boxed{\ \text{implied\_additions}_t = \Delta L_t + A_t \ }
$$

This is an **accounting identity**, derived from $L_t = L_{t-1} + \text{additions} - A_t$.

**It is not observed referrals.** NHS England does not publish referrals at this grain.
The identity absorbs referrals, validation removals, transfers and reporting changes
into a single residual. This is why the product never uses the word "demand", and
instead says *observed waiting-list pressure*.

$$
\text{activity\_gap\_pct} = \text{backlog\_growth\_3m\_pct} - \text{activity\_change\_3m\_pct}
$$

Positive means the backlog is growing faster than activity.

---

## 3. Normalisation

Two schemes, chosen per component according to whether **ordering** or **magnitude**
carries the information.

### 3.1 Percentile rank

$$
P(x_i) = \frac{\operatorname{rank}(x_i)}{n} \times 100
$$

Average ranks for ties. NaN stays NaN. A single valid observation scores a neutral 50.

Used where only relative position is meaningful (growth rates, long-wait share, forecast
change).

### 3.2 Clipped robust scaling

$$
S(x_i) = \operatorname{clip}\!\left( \frac{x_i - q_{0.05}}{q_{0.95} - q_{0.05}} \times 100,\ 0,\ 100 \right)
$$

Used for the 18-week gap, where a 40-point shortfall really is worse than a 20-point one
even if both sit in the same percentile bucket.

### 3.3 Why not min-max

Naive min-max scaling is
$(x - \min)/(\max - \min)$. With one extreme provider, every other organisation is
compressed into the bottom few percent of the range and the component stops
discriminating. This is asserted by test
(`test_outlier_does_not_compress_the_rest`): after adding an outlier three orders of
magnitude larger, the remaining 20 observations must still span more than 50 points.

---

## 4. Priority score

$$
\text{Priority} =
0.30 \cdot C_{\text{backlog}} +
0.25 \cdot C_{\text{longwait}} +
0.20 \cdot C_{\text{perf}} +
0.15 \cdot C_{\text{forecast}} +
0.10 \cdot C_{\text{persist}}
$$

with each $C \in [0, 100]$, so $\text{Priority} \in [0, 100]$.

Components are normalised **cross-sectionally within the latest reporting month**. The
score is therefore a statement about *relative position among peers in that month*, not
absolute severity. A month in which every service improved would still produce a full
0–100 spread.

### 4.1 Backlog growth pressure (30%)

$$
C_{\text{backlog}} = 0.65 \cdot P(\text{growth\_3m\_pct}) + 0.35 \cdot P(\text{slope\_6m\_pct\_of\_list})
$$

Weighted towards the shorter window: operational teams act on what is happening now,
with the longer slope as corroboration.

### 4.2 Long-wait burden (25%)

$$
C_{\text{longwait}} = \frac{\sum_b w_b \cdot P(\text{pct\_over\_}b)}{\sum_b w_b}
\qquad w_{52}=0.5,\ w_{65}=0.3,\ w_{78}=0.2
$$

A band is **skipped** if it is zero across the whole population. This matters: 78+ week
waits are now largely eliminated nationally, and percentile-ranking an all-zero column
would manufacture differences that do not exist. If no long-wait band is populated, the
component falls back to `pct_over_18_weeks`, which is always published.

### 4.3 18-week performance gap (20%)

$$
\text{gap}_i = \max(0,\ 92 - \text{pct\_within\_18\_weeks}_i)
$$

$$
C_{\text{perf}} = 0.75 \cdot S(\text{gap}) + 0.25 \cdot P(-\Delta_{3m}\text{pct\_within\_18})
$$

92% is the operational standard referenced in the NHS Constitution. It is applied here
as a **comparison benchmark**, not a claim about any organisation's contractual target,
and it is configurable via `REFERRAL_TO_TREATMENT_BENCHMARK`.

### 4.4 Forecast deterioration risk (15%)

$$
C_{\text{forecast}} = P(\text{forecast\_change\_3m\_pct})
$$

Series without a forecast score a **neutral 50**, not zero — a missing forecast should
neither reward nor punish a service.

### 4.5 Trend persistence (10%)

$$
C_{\text{persist}} = 0.6 \cdot \text{share\_rising\_6m} + 0.4 \cdot \left( \frac{\min(\text{run}, 4)}{4} \times 100 \right)
$$

`share_rising_6m` is already a percentage, so it needs no rescaling. The consecutive run
saturates at 4 months — beyond that, "persistent" is established and further months add
no information.

### 4.6 Bands

| Band | Range |
|---|---|
| LOW | 0 – 24 |
| MODERATE | 25 – 49 |
| HIGH | 50 – 74 |
| CRITICAL | 75 – 100 |

### 4.7 Decomposability

Every component's contribution $w_k \cdot C_k / 100$ is stored alongside the total, so:

$$
\sum_k \text{contribution}_k = \text{Priority}
$$

This is enforced by `test_contributions_sum_to_total` (tolerance 0.15 for rounding). It
is what makes the "why this score?" panel possible — the explanation is computed from
the same object that produced the number, so the two cannot drift apart.

### 4.8 Ranking threshold and withheld scores

Services with $L_t < 200$ are **excluded from the scoring basis**. A 40-pathway list can
post 50% growth from a handful of referrals; letting it top a national ranking would
make the product useless.

Because every component is a cross-sectional statistic computed on that basis, a service
outside it would receive the neutral fallback of 50 on all five components — giving a
total of exactly 50, which lands in **HIGH**. That would present roughly 1,400 tiny
services (including some with an empty waiting list) as uniformly high-priority, which
is an artefact of the defaults rather than a finding.

Such services are therefore reported as **`UNSCORED`** with a null score. Their raw
published metrics are shown in full, and the interface explains why no score is given.
Only the score is withheld, not the data.

If fewer than 30 services clear the threshold — which can happen on a heavily filtered
or very small dataset — scoring falls back to the full population and a warning is
logged, so the product still produces a usable ranking rather than nothing.

---

## 5. Forecasting

### 5.1 Models

**Naive drift** — the benchmark every other model must beat:

$$
\hat{L}_{T+h} = L_T + h \cdot \frac{L_T - L_1}{T - 1}
$$

**Linear trend** — OLS on a time index, full window or trailing 6 months:

$$
\hat{L}_{T+h} = \hat{\alpha} + \hat{\beta}(T + h)
$$

**Holt linear** — double exponential smoothing:

$$
\ell_t = \alpha L_t + (1-\alpha)(\ell_{t-1} + b_{t-1}), \qquad
b_t = \beta(\ell_t - \ell_{t-1}) + (1-\beta) b_{t-1}
$$
$$
\hat{L}_{T+h} = \ell_T + h \cdot b_T
$$

$\alpha \in [0.1, 0.9]$, $\beta \in [0.05, 0.65]$ chosen by grid search minimising
in-sample one-step SSE. A coarse grid is adequate for 12–24 points and is fully
transparent.

**Damped trend** — Holt with a damping parameter:

$$
\hat{L}_{T+h} = \ell_T + b_T \sum_{i=1}^{h} \phi^i, \qquad \phi \in \{0.75, 0.85, 0.95\}
$$

Waiting-list growth rarely continues linearly for six months. Damping pulls longer
horizons back towards the current level, which is usually the more defensible
operational assumption.

### 5.2 Model selection

Expanding-window **rolling-origin backtesting**. For origins
$k = k_0, \ldots, T-h$: train on $L_{1..k}$, predict $L_{k+h}$.

$$
\text{MAE} = \frac{1}{K}\sum_{k} \left| \hat{L}_k - L_k \right|
\qquad
\text{RMSE} = \sqrt{\frac{1}{K}\sum_{k} (\hat{L}_k - L_k)^2}
$$

$$
\text{MAPE} = \frac{1}{K}\sum_{k} \frac{|\hat{L}_k - L_k|}{|L_k|} \times 100
\qquad (\text{skipping } |L_k| \approx 0)
$$

The model with the **lowest one-step out-of-sample MAE** wins and is refit on the full
series. Minimum training size 5, up to 6 folds.

### 5.3 Skill against naive

$$
\text{skill} = 1 - \frac{\text{MAE}_{\text{model}}}{\text{MAE}_{\text{naive}}}
$$

Positive means the model genuinely beats "assume next month looks like this month". On
the reference build only **54.8%** of series clear that bar, and `naive_drift` is the
selected model for 901 of 2,078 series (43%). This is published in the product rather
than hidden — it is a real property of slow-moving waiting-list series.

### 5.4 Prediction intervals

$$
\hat{L}_{T+h} \pm z \cdot \sigma \cdot \sqrt{h}, \qquad z = 1.28
$$

$\sigma$ is the in-sample residual standard deviation; $\sqrt{h}$ widening is the
random-walk assumption. $z = 1.28$ gives a nominal **80%** band.

**Why 80% and not 95%.** With 12–24 observations a 95% band on these series is so wide
it stops being decision-useful. The honest framing is "this is an indicative range", not
"this is a rigorous confidence interval", and the product says exactly that. The
interval is also floored at zero: a waiting list cannot be negative.

### 5.5 Insufficient history

Fewer than **6** usable monthly observations returns `insufficient_history` with an
explanatory message. No number is fabricated. On the reference build, 1,487 of 3,565
series fall into this category and are reported as such.

Interior gaps of up to 2 months are linearly interpolated; longer gaps disqualify the
series.

### 5.6 Confidence labels

| Label | Condition |
|---|---|
| High | backtest MAPE ≤ 3% and ≥ 3 folds |
| Moderate | backtest MAPE ≤ 8% |
| Low | otherwise, or fewer than 2 folds |
| Insufficient data | no backtest possible |

Derived from **out-of-sample** error, never in-sample fit. The thresholds are judgement
calls and are stated as such.

---

## 6. Scenario model

### 6.1 Formulation

$$
A_{\text{extra}} = \frac{u}{100} \cdot \overline{A}_{3m}
$$

$$
\boxed{\ B_{\text{scenario}}(h) = \max\left(0,\ \hat{L}_{T+h} - h \cdot A_{\text{extra}}\right)\ }
$$

Cumulative in $h$ because each additional month of higher activity removes further
pathways. Floored at zero.

### 6.2 Uplift to stabilise

Solving $B(h) = L_T$ for $u$:

$$
u^{*} = \frac{\hat{L}_{T+3} - L_T}{3 \cdot \overline{A}_{3m}} \times 100
$$

Returns 0 when the baseline projection does not indicate growth, and is flagged as
infeasible above 100%.

**Worked example** (real service, reference build): current list 3,423; 3-month forecast
3,589; mean monthly activity 485 (figures from an earlier build vintage; the
arithmetic is what matters).

$$
u^{*} = \frac{3589 - 3423}{3 \times 485} \times 100 = 11.4\%
$$

### 6.3 What this is not

This is an **accounting projection**, not causal inference:

- No counterfactual is identified anywhere in the published data.
- Referral behaviour, case mix, clinical urgency and validation practice are assumed
  unchanged. Additional capacity can change all of them.
- The model does not assess whether an uplift is **achievable** — workforce, theatre,
  estate and diagnostic constraints are not represented, because they are not published
  at this grain.
- One-for-one removal is an assumption, not an observation.

Every scenario result carries its assumption list and the label *"Illustrative capacity
scenario, not a causal prediction."*

### 6.4 Enforced invariants

| Invariant | Test |
|---|---|
| $u = 0 \Rightarrow B_{\text{scenario}} = \hat{L}$ exactly | `test_zero_uplift_equals_baseline` |
| $u_1 > u_2 \Rightarrow B(u_1) \leq B(u_2)$ at every horizon | `test_more_activity_never_increases_backlog` |
| $B \geq 0$ always | `test_backlog_never_negative` |
| Effect accumulates with horizon | `test_effect_accumulates_with_horizon` |

---

## 7. Data quality

$$
Q = 0.40 \cdot Q_{\text{comp}} + 0.25 \cdot Q_{\text{cons}} + 0.20 \cdot Q_{\text{fresh}} + 0.15 \cdot Q_{\text{anom}}
$$

The weights are a **stated judgement**, not a standard. They are published in-app so a
reviewer can disagree with them explicitly.

### 7.1 Completeness (40%)

$$
Q_{\text{comp}} = 0.6 \cdot \underbrace{\frac{\text{populated key cells}}{\text{total key cells}} \times 100}_{\text{value}}
+ 0.4 \cdot \underbrace{\frac{\text{observed rows}}{\text{series} \times \text{months}} \times 100}_{\text{panel}}
$$

Panel completeness detects **interior gaps**: a series that reported in January and March
but not February is flagged, which is more interesting than one that simply never
appeared.

### 7.2 Consistency (25%)

$$
Q_{\text{cons}} = \frac{\text{checks passed}}{\text{checks run}} \times 100
$$

Checks: duplicate grain · negative counts · `within_18 ≤ total` · band nesting
($52^+ \geq 65^+ \geq 78^+ \geq 104^+$) · percentages in $[0, 100]$ · **reconciliation of
recomputed percentages against published values** (0.5 pp tolerance).

That last check is unusual and worth noting: it validates *our own derivation*, not just
the source.

### 7.3 Freshness (20%)

$$
Q_{\text{fresh}} = \operatorname{clip}\big(100 - 15 \cdot \max(0,\ \text{lag} - 2),\ 0,\ 100\big)
$$

NHS England publishes RTT roughly six to eight weeks in arrears, so a two-month lag is
normal and scores full marks.

### 7.4 Anomaly burden (15%)

Robust z-score using median and MAD:

$$
z_i = \frac{\Delta L_i - \operatorname{median}(\Delta L)}{1.4826 \cdot \operatorname{MAD}(\Delta L)}
$$

The 1.4826 constant makes MAD a consistent estimator of $\sigma$ under normality. Median
and MAD are used rather than mean and sd because the mean and sd are themselves
distorted by the outliers being detected.

Flagged when $|z| > 3.5$ **and** $|\Delta L| \geq 50$. The absolute floor prevents a
30-pathway list generating a flag from a swing of 10.

$$
Q_{\text{anom}} = \operatorname{clip}(100 - 20 \cdot \text{anomaly rate \%},\ 0,\ 100)
$$

### 7.5 Framing

Findings are **items requiring review**, never assertions that the published data is
wrong. Public statistics contain legitimate reporting changes, organisational mergers
and genuine operational step-changes that an automated check cannot distinguish from a
data problem. Every anomaly description ends: *"May reflect a genuine operational
change, a reporting change or a data issue."*

---

## 8. Narrative generation

Deterministic rules over computed values. **No language model in the default path.**

Rules:

1. A section is emitted **only** if its underlying metric is present and finite. Missing
   data produces no sentence — never a plausible-sounding default.
2. Score drivers are ordered by **actual contribution**, so the first bullet is always
   the largest single reason.
3. Recommended actions are triggered by explicit thresholds, each traceable to the value
   that fired it.
4. Every briefing carries caveats about data source, forecast uncertainty and scenario
   labelling.

Tested by `test_briefing_omits_sections_without_data` and
`test_no_fabricated_performance_claims`, which asserts that phrases implying achieved
outcomes ("reduced waiting", "saved", "improved patient outcomes") never appear.

### Optional LLM mode

Disabled unless `ANTHROPIC_API_KEY` is supplied **and** `LLM_BRIEFING_ENABLED=true`.
When enabled it only rephrases already-computed facts into prose, receives aggregate
metrics only, and its output is clearly labelled as AI-generated. The product is fully
functional without it — no portfolio-critical feature depends on a paid API.

---

## 9. Reproducibility

```bash
make setup   # install
make data    # ingest + build      (or: make demo)
make check   # lint + typecheck + test
make dev     # run
```

Determinism:

- The demo generator uses a fixed seed (`20260101`).
- Model grid search is deterministic — no random initialisation.
- Downloads are cached and checksummed; `--offline` rebuilds from cached files.
- Every source file's URL, checksum, row count and publication date is recorded in
  `ingestion_audit`.

The one non-deterministic input is NHS England itself: they revise published months, so
a rebuild months later may produce different figures. That is why the audit table
records the vintage retrieved.
