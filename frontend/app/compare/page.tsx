"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import PriorityBadge from "@/components/PriorityBadge";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  WarehouseMissingState,
} from "@/components/States";
import { api } from "@/lib/api";
import {
  fmtCompact,
  fmtCount,
  fmtPct,
  fmtScore,
  fmtSignedPct,
} from "@/lib/format";
import { useApiData } from "@/lib/useApiData";
import { useReferenceData } from "@/lib/useReferenceData";
import type { ComparisonResponse } from "@/types/api";

const MAX_PROVIDERS = 5;

// Distinguishable in both colour and, via the legend order, position.
const SERIES_COLOURS = ["#005eb8", "#b91c1c", "#007f3b", "#a16207", "#330072"];

export default function ComparePage() {
  const reference = useReferenceData();
  const { providers, specialties } = reference.data;

  // Explicit user choices; when unset the page derives a sensible default from
  // the reference data so it is immediately useful rather than an empty form.
  const [specialtyChoice, setSpecialtyChoice] = useState<string | null>(null);
  const [selectionChoice, setSelectionChoice] = useState<string[] | null>(null);

  const specialtyCode =
    specialtyChoice ?? specialties[0]?.specialty_code ?? "";
  const selected =
    selectionChoice ?? providers.slice(0, 3).map((p) => p.provider_code);

  const queryKey = JSON.stringify({ specialtyCode, selected });
  const fetcher = useCallback(
    async (signal: AbortSignal): Promise<ComparisonResponse | null> => {
      const query = JSON.parse(queryKey) as {
        specialtyCode: string;
        selected: string[];
      };
      if (!query.specialtyCode || query.selected.length === 0) return null;
      return api.compare(query.specialtyCode, query.selected, signal);
    },
    [queryKey],
  );

  const { data, error, loading, reload } =
    useApiData<ComparisonResponse | null>(fetcher);

  function toggleProvider(code: string) {
    const current = selected;
    if (current.includes(code)) {
      setSelectionChoice(current.filter((c) => c !== code));
    } else if (current.length < MAX_PROVIDERS) {
      setSelectionChoice([...current, code]);
    }
  }

  const labelFor = useMemo(() => {
    const map = new Map(
      providers.map((p) => [
        p.provider_code,
        p.provider_short_name ?? p.provider_name,
      ]),
    );
    return (code: string) => map.get(code) ?? code;
  }, [providers]);

  // Trend rows: one row per month, one column per selected provider.
  const trendRows = useMemo(() => {
    if (!data) return [];
    const months = new Set<string>();
    Object.values(data.history).forEach((points) =>
      points.forEach((p) => months.add(p.month_key)),
    );
    return Array.from(months)
      .sort()
      .map((month) => {
        const row: Record<string, string | number | null> = {
          label: month,
        };
        for (const [code, points] of Object.entries(data.history)) {
          const point = points.find((p) => p.month_key === month);
          row[code] = point?.waiting_list ?? null;
          row[`${code}__w18`] = point?.pct_within_18_weeks ?? null;
        }
        return row;
      });
  }, [data]);

  const barRows = useMemo(
    () =>
      data?.providers.map((row) => ({
        label: labelFor(row.provider_code),
        within18: row.pct_within_18_weeks ?? 0,
        growth: row.backlog_growth_3m_pct ?? 0,
        priority: row.priority_score ?? 0,
        longWait: row.pct_over_52_weeks ?? 0,
      })) ?? [],
    [data, labelFor],
  );

  const failure = error ?? reference.error;

  if (failure?.isWarehouseMissing) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <WarehouseMissingState message={failure.message} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 sm:px-6">
      <header>
        <p className="label text-brand-700">Peer benchmarking</p>
        <h1 className="mt-1 text-xl font-bold tracking-tight text-ink sm:text-2xl">
          Provider comparison
        </h1>
        <p className="mt-1 text-sm text-ink-muted">
          Benchmark up to {MAX_PROVIDERS} providers within one treatment
          function, against the specialty peer median.
        </p>
      </header>

      {/* --- Selection --------------------------------------------------- */}
      <section className="card p-4" aria-labelledby="selection-heading">
        <h2 id="selection-heading" className="sr-only">
          Comparison selection
        </h2>

        <div className="grid gap-4 lg:grid-cols-4">
          <div>
            <label htmlFor="compare-specialty" className="label mb-1 block">
              Treatment function
            </label>
            <select
              id="compare-specialty"
              className="control"
              value={specialtyCode}
              onChange={(e) => setSpecialtyChoice(e.target.value)}
            >
              {specialties.map((s) => (
                <option key={s.specialty_code} value={s.specialty_code}>
                  {s.specialty_short_name ?? s.specialty_name}
                </option>
              ))}
            </select>
          </div>

          <div className="lg:col-span-3">
            <p className="label mb-1">
              Providers ({selected.length}/{MAX_PROVIDERS} selected)
            </p>
            <div className="max-h-36 overflow-y-auto rounded-md border border-surface-border bg-surface-subtle p-2">
              <ul className="flex flex-wrap gap-1.5">
                {providers.map((provider) => {
                  const active = selected.includes(provider.provider_code);
                  const disabled = !active && selected.length >= MAX_PROVIDERS;
                  return (
                    <li key={provider.provider_code}>
                      <button
                        type="button"
                        onClick={() => toggleProvider(provider.provider_code)}
                        disabled={disabled}
                        aria-pressed={active}
                        className={`rounded-full border px-2.5 py-1 text-2xs font-medium transition-colors ${
                          active
                            ? "border-brand-700 bg-brand-700 text-white"
                            : "border-surface-border bg-surface text-ink-muted hover:bg-surface-muted"
                        } disabled:cursor-not-allowed disabled:opacity-40`}
                      >
                        {provider.provider_short_name ?? provider.provider_name}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {failure && (
        <ErrorState
          title="Could not load the comparison"
          message={failure.message}
          remedy={failure.remedy}
          onRetry={() => {
            reload();
            reference.reload();
          }}
        />
      )}

      {loading && !data && <CardSkeleton height="h-64" />}

      {!loading && selected.length === 0 && (
        <EmptyState
          title="Select at least one provider"
          message="Choose providers above to compare their position in this treatment function."
        />
      )}

      {data && data.providers.length > 0 && (
        <>
          {/* --- Comparison table ------------------------------------- */}
          <section className="card" aria-labelledby="compare-table-heading">
            <div className="card-header">
              <div>
                <h2 id="compare-table-heading" className="card-title">
                  {data.specialty_name}
                </h2>
                <p className="card-subtitle">
                  Latest reporting month, with the specialty peer median for
                  context
                </p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] text-sm">
                <caption className="sr-only">
                  Selected providers compared within {data.specialty_name}
                </caption>
                <thead>
                  <tr className="table-head">
                    <th scope="col" className="px-4 py-2.5 text-left">
                      Provider
                    </th>
                    <th scope="col" className="px-4 py-2.5 text-right">
                      Priority
                    </th>
                    <th scope="col" className="px-4 py-2.5 text-right">
                      Waiting list
                    </th>
                    <th scope="col" className="px-4 py-2.5 text-right">
                      3M growth
                    </th>
                    <th scope="col" className="px-4 py-2.5 text-right">
                      Within 18w
                    </th>
                    <th scope="col" className="px-4 py-2.5 text-right">
                      52w+
                    </th>
                    <th scope="col" className="px-4 py-2.5 text-right">
                      Forecast 3M
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-border">
                  {data.providers.map((row) => (
                    <tr key={row.provider_code} className="hover:bg-surface-subtle">
                      <td className="px-4 py-2.5">
                        <Link
                          href={`/service/${encodeURIComponent(
                            row.provider_code,
                          )}/${encodeURIComponent(row.specialty_code)}`}
                          className="font-medium text-brand-700 hover:underline"
                        >
                          {row.provider_short_name ?? row.provider_name}
                        </Link>
                      </td>
                      <td className="whitespace-nowrap px-4 py-2.5 text-right">
                        <span className="inline-flex items-center gap-2">
                          <span className="tnum font-semibold">
                            {fmtScore(row.priority_score)}
                          </span>
                          <PriorityBadge band={row.priority_band} />
                        </span>
                      </td>
                      <td className="tnum px-4 py-2.5 text-right">
                        {fmtCount(row.total_incomplete_pathways)}
                      </td>
                      <td className="tnum px-4 py-2.5 text-right">
                        {fmtSignedPct(row.backlog_growth_3m_pct)}
                      </td>
                      <td className="tnum px-4 py-2.5 text-right">
                        {fmtPct(row.pct_within_18_weeks)}
                      </td>
                      <td className="tnum px-4 py-2.5 text-right">
                        {fmtPct(row.pct_over_52_weeks, 2)}
                      </td>
                      <td className="tnum px-4 py-2.5 text-right">
                        {row.forecast_status === "ok"
                          ? fmtSignedPct(row.forecast_change_3m_pct)
                          : "n/a"}
                      </td>
                    </tr>
                  ))}

                  <tr className="bg-surface-muted font-medium">
                    <th scope="row" className="px-4 py-2.5 text-left text-ink-muted">
                      Specialty peer median
                    </th>
                    <td className="tnum px-4 py-2.5 text-right text-ink-muted">
                      {fmtScore(data.peer_median.priority_score)}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-muted">
                      {fmtCount(data.peer_median.total_incomplete_pathways)}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-muted">
                      {fmtSignedPct(data.peer_median.backlog_growth_3m_pct)}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-muted">
                      {fmtPct(data.peer_median.pct_within_18_weeks)}
                    </td>
                    <td className="tnum px-4 py-2.5 text-right text-ink-muted">
                      {fmtPct(data.peer_median.pct_over_52_weeks, 2)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-ink-subtle">—</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="border-t border-surface-border px-4 py-2.5 text-2xs text-ink-subtle">
              Peer benchmark computed from the loaded data across all providers
              reporting this treatment function. Not an official NHS England
              benchmark. Median is used rather than mean because provider
              distributions are strongly right-skewed.
            </p>
          </section>

          {/* --- Charts ----------------------------------------------- */}
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <section className="card" aria-labelledby="trend-compare-heading">
              <div className="card-header">
                <h2 id="trend-compare-heading" className="card-title">
                  Waiting list trend
                </h2>
              </div>
              <div className="p-5">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={trendRows} margin={{ top: 8, right: 8, left: 4 }}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#dbe3ef"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 10, fill: "#5f6b82" }}
                      tickLine={false}
                      axisLine={{ stroke: "#dbe3ef" }}
                      interval="preserveStartEnd"
                      minTickGap={24}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "#5f6b82" }}
                      tickLine={false}
                      axisLine={false}
                      width={52}
                      tickFormatter={(v) => fmtCompact(v as number)}
                    />
                    <Tooltip
                      formatter={(v, n) => [fmtCount(v as number), labelFor(n as string)]}
                      contentStyle={{
                        fontSize: 12,
                        borderRadius: 8,
                        border: "1px solid #dbe3ef",
                      }}
                    />
                    <Legend
                      wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      iconType="plainline"
                      formatter={(value) => labelFor(value as string)}
                    />
                    {selected.map((code, index) => (
                      <Line
                        key={code}
                        type="monotone"
                        dataKey={code}
                        stroke={SERIES_COLOURS[index % SERIES_COLOURS.length]}
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                        isAnimationActive={false}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="card" aria-labelledby="bars-heading">
              <div className="card-header">
                <h2 id="bars-heading" className="card-title">
                  18-week performance and priority
                </h2>
              </div>
              <div className="p-5">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart
                    data={barRows}
                    margin={{ top: 8, right: 8, left: 4, bottom: 4 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#dbe3ef"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 9, fill: "#5f6b82" }}
                      tickLine={false}
                      axisLine={{ stroke: "#dbe3ef" }}
                      interval={0}
                      angle={-15}
                      textAnchor="end"
                      height={54}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: "#5f6b82" }}
                      tickLine={false}
                      axisLine={false}
                      width={44}
                      domain={[0, 100]}
                    />
                    <Tooltip
                      formatter={(v, n) => [
                        `${(v as number).toFixed(1)}${n === "Priority score" ? "" : "%"}`,
                        n as string,
                      ]}
                      contentStyle={{
                        fontSize: 12,
                        borderRadius: 8,
                        border: "1px solid #dbe3ef",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                    {typeof data.peer_median.pct_within_18_weeks === "number" && (
                      <ReferenceLine
                        y={data.peer_median.pct_within_18_weeks}
                        stroke="#5f6b82"
                        strokeDasharray="4 4"
                        label={{
                          value: "Peer median (18w)",
                          fontSize: 9,
                          fill: "#3d4759",
                          position: "right",
                        }}
                      />
                    )}
                    <Bar
                      dataKey="within18"
                      name="Within 18 weeks"
                      fill="#007f3b"
                      radius={[3, 3, 0, 0]}
                      isAnimationActive={false}
                    />
                    <Bar
                      dataKey="priority"
                      name="Priority score"
                      fill="#005eb8"
                      radius={[3, 3, 0, 0]}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
        </>
      )}
    </div>
  );
}
