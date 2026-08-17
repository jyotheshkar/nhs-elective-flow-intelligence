"use client";

import Link from "next/link";
import { use, useCallback } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import ExecutiveBrief from "@/components/ExecutiveBrief";
import PriorityBadge from "@/components/PriorityBadge";
import ScenarioSimulator from "@/components/ScenarioSimulator";
import ScoreBreakdown from "@/components/ScoreBreakdown";
import {
  CardSkeleton,
  ErrorState,
  WarehouseMissingState,
} from "@/components/States";
import WaitingListTrendChart from "@/components/charts/WaitingListTrendChart";
import { api } from "@/lib/api";
import { useApiData } from "@/lib/useApiData";
import {
  TONE_CLASS,
  fmtCompact,
  fmtCount,
  fmtDecimal,
  fmtPct,
  fmtSignedPct,
  isNum,
  movementTone,
} from "@/lib/format";
import type { ServiceDetailResponse, TimeseriesPoint } from "@/types/api";

export default function ServiceDetailPage({
  params,
}: {
  params: Promise<{ providerCode: string; specialtyCode: string }>;
}) {
  const { providerCode, specialtyCode } = use(params);

  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.serviceDetail(
        decodeURIComponent(providerCode),
        decodeURIComponent(specialtyCode),
        10,
        signal,
      ),
    [providerCode, specialtyCode],
  );

  const { data, error, reload } = useApiData<ServiceDetailResponse>(fetcher);

  if (error?.isWarehouseMissing) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <WarehouseMissingState message={error.message} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <ErrorState
          title="Could not load this service"
          message={error.message}
          remedy={error.remedy}
          onRetry={reload}
        />
        <Link href="/" className="btn mt-4">
          ← Back to the control room
        </Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 sm:px-6">
        <div className="skeleton h-10 w-2/3" />
        <div className="grid gap-5 lg:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      </div>
    );
  }

  const { service, forecast, briefing, score_components, history } = data;

  // Forecast horizons rendered as chart points appended to history.
  const forecastPoints: TimeseriesPoint[] = forecast.points
    .filter((p) => isNum(p.value))
    .map((p) => ({
      month_key: p.month_key ?? "",
      month_label: null,
      waiting_list: p.value ?? null,
      is_forecast: true,
      forecast_lower: p.lower ?? null,
      forecast_upper: p.upper ?? null,
    }));

  const longWaitRows = history.map((point) => ({
    label: point.month_label ?? point.month_key,
    within18: point.within_18_weeks ?? 0,
    over18:
      (point.waiting_list ?? 0) -
      (point.within_18_weeks ?? 0) -
      (point.over_52_weeks ?? 0),
    over52: point.over_52_weeks ?? 0,
  }));

  const activityRows = history.map((point) => ({
    label: point.month_label ?? point.month_key,
    admitted: point.admitted_activity ?? null,
    nonAdmitted: point.non_admitted_activity ?? null,
    total: point.completed_pathways ?? null,
  }));

  const hasActivity = activityRows.some((r) => isNum(r.total));

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 sm:px-6">
      {/* --- Header ------------------------------------------------------ */}
      <header>
        <nav aria-label="Breadcrumb" className="mb-2">
          <ol className="flex flex-wrap items-center gap-1.5 text-xs text-ink-subtle">
            <li>
              <Link href="/" className="hover:text-ink hover:underline">
                Control Room
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li>
              <Link
                href={`/rankings?provider_code=${encodeURIComponent(
                  service.provider_code,
                )}`}
                className="hover:text-ink hover:underline"
              >
                {service.provider_short_name ?? service.provider_name}
              </Link>
            </li>
            <li aria-hidden="true">/</li>
            <li className="font-medium text-ink-muted">
              {service.specialty_short_name ?? service.specialty_name}
            </li>
          </ol>
        </nav>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">
              {service.specialty_name}
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              {service.provider_name}
              {service.region_name ? ` · ${service.region_name}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="label">Priority score</p>
              <p className="tnum text-3xl font-bold leading-none text-ink">
                {fmtDecimal(service.priority_score, 0)}
                <span className="text-base font-normal text-ink-subtle">
                  {" "}
                  / 100
                </span>
              </p>
            </div>
            <PriorityBadge band={service.priority_band} size="md" />
          </div>
        </div>

        {!service.is_rankable && (
          <p className="mt-3 rounded-md border border-band-moderateBorder bg-band-moderateBg px-3 py-2 text-xs leading-relaxed text-band-moderate">
            <strong>No priority score is given for this service.</strong> Its
            waiting list is below the ranking threshold, and percentage growth
            on a small list is dominated by noise. The published measures below
            are shown in full; only the derived score is withheld.
          </p>
        )}
      </header>

      {/* --- Performance overview --------------------------------------- */}
      <section aria-labelledby="overview-heading">
        <h2 id="overview-heading" className="sr-only">
          Performance overview
        </h2>
        <ul className="grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Kpi
            label="Waiting list"
            value={fmtCount(service.total_incomplete_pathways)}
            sub={`${fmtSignedPct(service.backlog_growth_1m_pct)} vs last month`}
            tone={movementTone(service.backlog_growth_1m_pct, false)}
          />
          <Kpi
            label="3-month growth"
            value={fmtSignedPct(service.backlog_growth_3m_pct)}
            sub={`${fmtSignedPct(service.backlog_growth_6m_pct)} over 6 months`}
            tone={movementTone(service.backlog_growth_3m_pct, false)}
          />
          <Kpi
            label="Within 18 weeks"
            value={fmtPct(service.pct_within_18_weeks)}
            sub={
              isNum(service.pct_within_18_weeks_change_3m)
                ? `${service.pct_within_18_weeks_change_3m >= 0 ? "+" : ""}${fmtDecimal(
                    service.pct_within_18_weeks_change_3m,
                  )} pp over 3 months`
                : "—"
            }
            tone={movementTone(service.pct_within_18_weeks_change_3m, true)}
          />
          <Kpi
            label="Waiting 52+ weeks"
            value={fmtCount(service.over_52_weeks)}
            sub={`${fmtPct(service.pct_over_52_weeks, 2)} of list`}
          />
          <Kpi
            label="Median wait"
            value={
              isNum(service.median_wait_weeks)
                ? `${fmtDecimal(service.median_wait_weeks)}w`
                : "—"
            }
            sub="Weeks since referral"
          />
          <Kpi
            label="Months to clear"
            value={
              isNum(service.months_to_clear_at_current_activity)
                ? fmtDecimal(service.months_to_clear_at_current_activity)
                : "—"
            }
            sub="At recent activity rate"
          />
        </ul>
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        {/* --- Trend + forecast ----------------------------------------- */}
        <section className="card xl:col-span-8" aria-labelledby="trend-heading">
          <div className="card-header">
            <div>
              <h2 id="trend-heading" className="card-title">
                Waiting list and forecast
              </h2>
              <p className="card-subtitle">
                {forecast.status === "ok"
                  ? `${forecast.history_months} months of history · ${forecast.model?.replace(/_/g, " ")} model · ${forecast.confidence.toLowerCase()} confidence`
                  : "Forecast unavailable for this service"}
              </p>
            </div>
            {forecast.status === "ok" && forecast.accuracy && (
              <div className="flex gap-4 text-right">
                <div>
                  <p className="label">Backtest MAPE</p>
                  <p className="tnum text-sm font-semibold text-ink">
                    {fmtPct(forecast.accuracy.mape, 2)}
                  </p>
                </div>
                <div>
                  <p className="label">Beats naive</p>
                  <p className="text-sm font-semibold text-ink">
                    {forecast.accuracy.beats_naive ? "Yes" : "No"}
                  </p>
                </div>
              </div>
            )}
          </div>
          <div className="p-5">
            <WaitingListTrendChart
              history={history}
              forecast={forecastPoints}
              height={300}
            />
            {forecast.status !== "ok" && (
              <p className="mt-3 rounded-md border border-surface-border bg-surface-subtle p-3 text-xs text-ink-muted">
                {forecast.message}
              </p>
            )}
            <p className="mt-3 text-2xs leading-relaxed text-ink-subtle">
              {forecast.method_note}
            </p>
          </div>
        </section>

        {/* --- Why this score ------------------------------------------- */}
        <section className="card xl:col-span-4" aria-labelledby="score-heading">
          <div className="card-header">
            <div>
              <h2 id="score-heading" className="card-title">
                Why this score?
              </h2>
              <p className="card-subtitle">
                Weighted contribution of each component
              </p>
            </div>
          </div>
          <div className="p-5">
            <ScoreBreakdown
              components={score_components}
              total={service.priority_score}
              drivers={briefing.drivers}
            />
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        {/* --- Long wait composition ------------------------------------ */}
        <section className="card xl:col-span-6" aria-labelledby="composition-heading">
          <div className="card-header">
            <div>
              <h2 id="composition-heading" className="card-title">
                Waiting list composition
              </h2>
              <p className="card-subtitle">
                Pathways by wait band, each reporting month
              </p>
            </div>
          </div>
          <div className="p-5">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={longWaitRows} margin={{ top: 8, right: 8, left: 4 }}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#e2e8f0"
                  vertical={false}
                />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: "#64748b" }}
                  tickLine={false}
                  axisLine={{ stroke: "#e2e8f0" }}
                  interval="preserveStartEnd"
                  minTickGap={20}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={(v) => fmtCompact(v as number)}
                />
                <Tooltip
                  formatter={(v, n) => [fmtCount(v as number), n as string]}
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #e2e8f0",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                <Bar
                  dataKey="within18"
                  stackId="a"
                  name="Within 18 weeks"
                  fill="#047857"
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="over18"
                  stackId="a"
                  name="18–52 weeks"
                  fill="#a16207"
                  isAnimationActive={false}
                />
                <Bar
                  dataKey="over52"
                  stackId="a"
                  name="52+ weeks"
                  fill="#b91c1c"
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        {/* --- Activity -------------------------------------------------- */}
        <section className="card xl:col-span-6" aria-labelledby="activity-heading">
          <div className="card-header">
            <div>
              <h2 id="activity-heading" className="card-title">
                Completed activity
              </h2>
              <p className="card-subtitle">
                Admitted and non-admitted completed pathways per month
              </p>
            </div>
          </div>
          <div className="p-5">
            {hasActivity ? (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart
                  data={activityRows}
                  margin={{ top: 8, right: 8, left: 4 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#e2e8f0"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 10, fill: "#64748b" }}
                    tickLine={false}
                    axisLine={{ stroke: "#e2e8f0" }}
                    interval="preserveStartEnd"
                    minTickGap={20}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#64748b" }}
                    tickLine={false}
                    axisLine={false}
                    width={52}
                    tickFormatter={(v) => fmtCompact(v as number)}
                  />
                  <Tooltip
                    formatter={(v, n) => [fmtCount(v as number), n as string]}
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid #e2e8f0",
                    }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                    iconType="plainline"
                  />
                  <Line
                    type="monotone"
                    dataKey="total"
                    name="Total completed"
                    stroke="#1e40af"
                    strokeWidth={2.25}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="admitted"
                    name="Admitted"
                    stroke="#0891b2"
                    strokeWidth={1.75}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    dataKey="nonAdmitted"
                    name="Non-admitted"
                    stroke="#7c3aed"
                    strokeWidth={1.75}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <p className="py-16 text-center text-sm text-ink-subtle">
                No completed-activity data is published for this service in the
                loaded period.
              </p>
            )}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        {/* --- Scenario -------------------------------------------------- */}
        <section className="card xl:col-span-7" aria-labelledby="scenario-heading">
          <div className="card-header">
            <div>
              <h2 id="scenario-heading" className="card-title">
                Capacity scenario simulator
              </h2>
              <p className="card-subtitle">
                Test how additional activity would change the modelled waiting
                list
              </p>
            </div>
          </div>
          <div className="p-5">
            <ScenarioSimulator
              providerCode={service.provider_code}
              specialtyCode={service.specialty_code}
              initial={data.scenario}
            />
          </div>
        </section>

        {/* --- Executive brief ------------------------------------------- */}
        <section className="card xl:col-span-5" aria-labelledby="brief-heading">
          <div className="card-header">
            <div>
              <h2 id="brief-heading" className="card-title">
                Executive brief
              </h2>
              <p className="card-subtitle">
                Management summary generated from computed values
              </p>
            </div>
          </div>
          <div className="p-5">
            <ExecutiveBrief briefing={briefing} />
          </div>
        </section>
      </div>

      {/* --- Peer context + quality ------------------------------------- */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <section className="card" aria-labelledby="peer-heading">
          <div className="card-header">
            <div>
              <h2 id="peer-heading" className="card-title">
                Peer context
              </h2>
              <p className="card-subtitle">
                Median across all providers reporting this specialty. A peer
                benchmark computed from the loaded data, not an official NHS
                England benchmark.
              </p>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-sm">
              <caption className="sr-only">
                This service compared with the specialty peer median
              </caption>
              <thead>
                <tr className="table-head">
                  <th scope="col" className="px-5 py-2.5 text-left">
                    Measure
                  </th>
                  <th scope="col" className="px-5 py-2.5 text-right">
                    This service
                  </th>
                  <th scope="col" className="px-5 py-2.5 text-right">
                    Peer median
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                <PeerRow
                  label="Within 18 weeks"
                  value={fmtPct(service.pct_within_18_weeks)}
                  peer={fmtPct(service.peer_median_pct_within_18_weeks)}
                />
                <PeerRow
                  label="3-month growth"
                  value={fmtSignedPct(service.backlog_growth_3m_pct)}
                  peer={fmtSignedPct(service.peer_median_backlog_growth_3m_pct)}
                />
                <PeerRow
                  label="Within 18 weeks (all specialties)"
                  value={fmtPct(service.pct_within_18_weeks)}
                  peer={fmtPct(service.national_median_pct_within_18_weeks)}
                />
              </tbody>
            </table>
          </div>
        </section>

        <section className="card" aria-labelledby="quality-heading">
          <div className="card-header">
            <div>
              <h2 id="quality-heading" className="card-title">
                Data quality for this service
              </h2>
              <p className="card-subtitle">
                {data.quality_issues.length === 0
                  ? "No issues flagged"
                  : `${data.quality_issues.length} item(s) flagged for review`}
              </p>
            </div>
            <Link href="/quality" className="btn btn-ghost text-xs">
              Full monitor →
            </Link>
          </div>
          <div className="p-5">
            {data.quality_issues.length === 0 ? (
              <p className="py-6 text-center text-sm text-ink-subtle">
                No data quality issues were flagged for this provider and
                specialty across the loaded reporting periods.
              </p>
            ) : (
              <ul className="space-y-3">
                {data.quality_issues.slice(0, 6).map((issue, index) => (
                  <li
                    key={index}
                    className="rounded-md border border-surface-border bg-surface-subtle p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold text-ink">
                        {String(issue.issue_type)}
                      </span>
                      <span className="rounded-full border border-surface-border bg-surface px-2 py-0.5 text-2xs font-medium text-ink-muted">
                        {String(issue.severity)}
                      </span>
                      {issue.month ? (
                        <span className="text-2xs text-ink-subtle">
                          {String(issue.month)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">
                      {String(issue.description)}
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub: string;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <li className="card p-4">
      <p className="label">{label}</p>
      <p className="tnum mt-1.5 text-xl font-semibold text-ink">{value}</p>
      <p className={`mt-0.5 text-2xs ${TONE_CLASS[tone]}`}>{sub}</p>
    </li>
  );
}

function PeerRow({
  label,
  value,
  peer,
}: {
  label: string;
  value: string;
  peer: string;
}) {
  return (
    <tr>
      <th scope="row" className="px-5 py-2.5 text-left font-normal text-ink-muted">
        {label}
      </th>
      <td className="tnum px-5 py-2.5 text-right font-semibold text-ink">
        {value}
      </td>
      <td className="tnum px-5 py-2.5 text-right text-ink-muted">{peer}</td>
    </tr>
  );
}
