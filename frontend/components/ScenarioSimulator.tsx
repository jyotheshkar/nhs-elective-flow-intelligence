"use client";

import { useCallback, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorState, LoadingSkeleton } from "@/components/States";
import { api } from "@/lib/api";
import {
  fmtCompact,
  fmtCount,
  fmtDecimal,
  fmtMonth,
  fmtSignedCount,
} from "@/lib/format";
import { useApiData } from "@/lib/useApiData";
import type { ScenarioResponse } from "@/types/api";

const PRESETS = [0, 5, 10, 15, 20];

interface Props {
  providerCode: string;
  specialtyCode: string;
  initial?: ScenarioResponse | null;
}

/**
 * Interactive activity-uplift simulator.
 *
 * Every rendering states plainly that outputs are modelled estimates under an
 * accounting projection. The assumptions list is expanded by default the first
 * time the panel is used, because a scenario without its assumptions is
 * misleading rather than merely incomplete.
 */
export default function ScenarioSimulator({
  providerCode,
  specialtyCode,
  initial,
}: Props) {
  const [uplift, setUplift] = useState(10);
  const [showAssumptions, setShowAssumptions] = useState(false);

  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.scenario(
        {
          provider_code: providerCode,
          specialty_code: specialtyCode,
          uplift_pct: uplift,
          compare_uplifts: PRESETS,
        },
        signal,
      ),
    [providerCode, specialtyCode, uplift],
  );

  const { data: fetched, error, loading, reload } =
    useApiData<ScenarioResponse>(fetcher);

  // Fall back to the server-rendered scenario until the first fetch resolves,
  // so the panel never flashes empty on load.
  const data = fetched ?? initial ?? null;

  if (error && !data) {
    return <ErrorState message={error.message} onRetry={reload} />;
  }

  if (!data && loading) {
    return <LoadingSkeleton rows={6} />;
  }

  if (data && data.status !== "ok") {
    return (
      <div className="rounded-md border border-surface-border bg-surface-subtle p-4">
        <p className="text-sm font-medium text-ink">
          Scenario modelling is not available for this service
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
          {data.message}
        </p>
      </div>
    );
  }

  const selected = data?.series.find((s) => s.uplift_pct === uplift);
  const baselinePoint = selected?.points.find((p) => p.horizon_months === 3);

  // Trajectory: baseline vs the selected uplift at each forecast horizon.
  const trajectoryRows =
    selected?.points.map((point) => ({
      label: point.month_key
        ? `+${point.horizon_months}m (${fmtMonth(point.month_key)})`
        : `+${point.horizon_months}m`,
      baseline: point.baseline_backlog,
      scenario: point.scenario_backlog,
    })) ?? [];

  // Chart: 3-month modelled backlog under each uplift.
  const chartRows =
    data?.series.map((series) => {
      const point = series.points.find((p) => p.horizon_months === 3);
      return {
        label: series.uplift_pct === 0 ? "Baseline" : `+${series.uplift_pct}%`,
        uplift: series.uplift_pct,
        backlog: point?.scenario_backlog ?? 0,
        difference: point?.difference_from_baseline ?? 0,
      };
    }) ?? [];

  return (
    <div className="space-y-5">
      {/* --- Controls --------------------------------------------------- */}
      <div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <label htmlFor="uplift-slider" className="label mb-1 block">
              Assumed monthly activity uplift
            </label>
            <p className="text-xs text-ink-subtle">
              Baseline activity:{" "}
              <span className="tnum font-semibold text-ink-muted">
                {fmtCount(data?.baseline_monthly_activity)}
              </span>{" "}
              completed pathways per month (3-month average)
            </p>
          </div>
          <p className="tnum text-2xl font-semibold text-brand-700">
            +{uplift}%
          </p>
        </div>

        <input
          id="uplift-slider"
          type="range"
          min={0}
          max={30}
          step={1}
          value={uplift}
          onChange={(e) => setUplift(Number(e.target.value))}
          className="mt-3 w-full accent-brand-700"
          aria-valuetext={`${uplift} percent activity uplift`}
        />

        <div className="mt-2 flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => setUplift(preset)}
              aria-pressed={uplift === preset}
              className={`btn h-7 px-2.5 text-xs ${
                uplift === preset ? "btn-primary" : ""
              }`}
            >
              {preset === 0 ? "Baseline" : `+${preset}%`}
            </button>
          ))}
        </div>
      </div>

      {/* --- Headline result -------------------------------------------- */}
      {baselinePoint && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-surface-border bg-surface-subtle p-3">
            <p className="label">Baseline in 3 months</p>
            <p className="tnum mt-1 text-lg font-semibold text-ink">
              {fmtCount(baselinePoint.baseline_backlog)}
            </p>
            <p className="mt-0.5 text-2xs text-ink-subtle">
              Forecast with no change in activity
            </p>
          </div>

          <div className="rounded-md border border-brand-200 bg-brand-50 p-3">
            <p className="label">Under +{uplift}% activity</p>
            <p className="tnum mt-1 text-lg font-semibold text-brand-800">
              {fmtCount(baselinePoint.scenario_backlog)}
            </p>
            <p className="mt-0.5 text-2xs text-brand-700">
              {fmtSignedCount(baselinePoint.difference_from_baseline)} pathways
              vs baseline
            </p>
          </div>

          <div className="rounded-md border border-surface-border bg-surface-subtle p-3">
            <p className="label">Uplift to stabilise</p>
            <p className="tnum mt-1 text-lg font-semibold text-ink">
              {data?.uplift_required_to_stabilise_pct === null ||
              data?.uplift_required_to_stabilise_pct === undefined
                ? "—"
                : `${fmtDecimal(data.uplift_required_to_stabilise_pct, 1)}%`}
            </p>
            <p className="mt-0.5 text-2xs text-ink-subtle">
              {data?.uplift_required_to_stabilise_pct === 0
                ? "List is not forecast to grow"
                : data?.stabilisation_feasible
                  ? "To hold the list at its current level over 3 months"
                  : "Exceeds a doubling of current activity"}
            </p>
          </div>
        </div>
      )}

      {/* --- Trajectory: baseline vs scenario --------------------------- */}
      {trajectoryRows.length > 1 && (
        <div>
          <p className="label mb-2">
            Modelled trajectory — baseline vs +{uplift}% activity
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart
              data={trajectoryRows}
              margin={{ top: 8, right: 12, left: 4, bottom: 4 }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="#dbe3ef"
                vertical={false}
              />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: "#5f6b82" }}
                tickLine={false}
                axisLine={{ stroke: "#dbe3ef" }}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#5f6b82" }}
                tickLine={false}
                axisLine={false}
                width={52}
                domain={["auto", "auto"]}
                tickFormatter={(v) => fmtCompact(v as number)}
              />
              <Tooltip
                formatter={(v, n) => [fmtCount(v as number), n as string]}
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  border: "1px solid #dbe3ef",
                }}
              />
              <Legend
                wrapperStyle={{ fontSize: 11, paddingTop: 6 }}
                iconType="plainline"
              />
              <Line
                type="monotone"
                dataKey="baseline"
                name="Baseline forecast (modelled)"
                stroke="#5f6b82"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={{ r: 3 }}
                isAnimationActive={false}
              />
              <Line
                type="monotone"
                dataKey="scenario"
                name={`Scenario +${uplift}% (modelled)`}
                stroke="#005eb8"
                strokeWidth={2.25}
                dot={{ r: 3, fill: "#005eb8" }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
          <p className="mt-1 text-2xs text-ink-subtle">
            Both lines are modelled projections, not published NHS England
            figures.
          </p>
        </div>
      )}

      {/* --- Comparison chart ------------------------------------------- */}
      {chartRows.length > 0 && (
        <div>
          <p className="label mb-2">
            Modelled waiting list in 3 months, by activity uplift
          </p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={chartRows}
              margin={{ top: 20, right: 8, left: 4, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#dbe3ef" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11, fill: "#5f6b82" }}
                tickLine={false}
                axisLine={{ stroke: "#dbe3ef" }}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#5f6b82" }}
                tickLine={false}
                axisLine={false}
                width={52}
                domain={["dataMin - 200", "dataMax + 200"]}
                tickFormatter={(v) => fmtCompact(v as number)}
              />
              <Tooltip
                formatter={(value) => [fmtCount(value as number), "Modelled list"]}
                contentStyle={{
                  fontSize: 12,
                  borderRadius: 8,
                  border: "1px solid #dbe3ef",
                }}
              />
              <Bar dataKey="backlog" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                {chartRows.map((row) => (
                  <Cell
                    key={row.label}
                    fill={row.uplift === uplift ? "#005eb8" : "#b9d9f0"}
                  />
                ))}
                <LabelList
                  dataKey="backlog"
                  position="top"
                  formatter={(v: unknown) => fmtCompact(v as number)}
                  style={{ fontSize: 10, fill: "#3d4759" }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* --- Disclaimer + assumptions ----------------------------------- */}
      <div className="rounded-md border border-band-moderateBorder bg-band-moderateBg p-3">
        <p className="text-xs font-semibold text-band-moderate">
          {data?.disclaimer}
        </p>
        <button
          type="button"
          onClick={() => setShowAssumptions((v) => !v)}
          aria-expanded={showAssumptions}
          className="mt-2 text-xs font-medium text-band-moderate underline underline-offset-2"
        >
          {showAssumptions ? "Hide" : "Show"} the {data?.assumptions.length ?? 0}{" "}
          assumptions behind this model
        </button>
        {showAssumptions && (
          <ul className="mt-2 space-y-1.5">
            {data?.assumptions.map((assumption) => (
              <li
                key={assumption}
                className="flex gap-2 text-2xs leading-relaxed text-ink-muted"
              >
                <span aria-hidden="true">•</span>
                <span>{assumption}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
