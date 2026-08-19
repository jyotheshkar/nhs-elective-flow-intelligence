"use client";

import { useRouter } from "next/navigation";
import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { fmtCount, fmtPct, fmtSignedPct } from "@/lib/format";
import { BAND_CHART_COLOURS } from "@/components/PriorityBadge";
import type { MatrixPoint } from "@/types/api";

interface Props {
  points: MatrixPoint[];
  height?: number;
}

/**
 * Two-dimensional pressure view: growth against long-wait burden.
 *
 * Deliberately a scatter and not a heatmap - the operational question is
 * "which individual services sit in the top-right quadrant?", which needs
 * identifiable points, not density. Clicking a point navigates to that
 * service, and the same information is available in the ranked table below for
 * anyone who cannot use a scatter plot.
 */
export default function PriorityMatrix({ points, height = 360 }: Props) {
  const router = useRouter();

  const data = points
    .filter(
      (point) =>
        typeof point.x_backlog_growth_3m_pct === "number" &&
        typeof point.y_long_wait_pct === "number",
    )
    .map((point) => ({
      x: point.x_backlog_growth_3m_pct as number,
      y: point.y_long_wait_pct as number,
      z: point.size_waiting_list ?? 0,
      band: point.priority_band ?? "UNSCORED",
      score: point.priority_score,
      provider: point.provider_name ?? point.provider_code,
      specialty: point.specialty_name ?? point.specialty_code,
      providerCode: point.provider_code,
      specialtyCode: point.specialty_code,
    }));

  if (data.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-ink-subtle">
        Not enough history in the current selection to plot growth against
        long-wait burden.
      </p>
    );
  }

  const medianY = median(data.map((d) => d.y));

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 12, right: 20, bottom: 32, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#dbe3ef" />
          <XAxis
            type="number"
            dataKey="x"
            name="3-month waiting-list growth"
            unit="%"
            tick={{ fontSize: 11, fill: "#5f6b82" }}
            tickLine={false}
            axisLine={{ stroke: "#dbe3ef" }}
            label={{
              value: "3-month waiting-list growth (%)",
              position: "insideBottom",
              offset: -18,
              fontSize: 11,
              fill: "#3d4759",
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Long-wait burden"
            unit="%"
            tick={{ fontSize: 11, fill: "#5f6b82" }}
            tickLine={false}
            axisLine={false}
            width={56}
            label={{
              value: "Long waits (% of list)",
              angle: -90,
              position: "insideLeft",
              offset: 8,
              fontSize: 11,
              fill: "#3d4759",
              style: { textAnchor: "middle" },
            }}
          />
          <ZAxis type="number" dataKey="z" range={[30, 520]} name="Waiting list" />

          {/* Quadrant guides: zero growth, and the median long-wait burden. */}
          <ReferenceLine x={0} stroke="#8494ad" strokeDasharray="3 3" />
          <ReferenceLine y={medianY} stroke="#8494ad" strokeDasharray="3 3" />

          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            contentStyle={{
              fontSize: 12,
              borderRadius: 8,
              border: "1px solid #dbe3ef",
            }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const d = payload[0].payload as (typeof data)[number];
              return (
                <div className="rounded-lg border border-surface-border bg-surface p-3 shadow-raised">
                  <p className="text-xs font-semibold text-ink">{d.specialty}</p>
                  <p className="text-2xs text-ink-subtle">{d.provider}</p>
                  <dl className="mt-2 space-y-0.5 text-2xs text-ink-muted">
                    <div className="flex justify-between gap-4">
                      <dt>Waiting list</dt>
                      <dd className="tnum font-semibold">{fmtCount(d.z)}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt>3-month growth</dt>
                      <dd className="tnum font-semibold">{fmtSignedPct(d.x)}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt>Long waits</dt>
                      <dd className="tnum font-semibold">{fmtPct(d.y, 2)}</dd>
                    </div>
                    <div className="flex justify-between gap-4">
                      <dt>Priority</dt>
                      <dd className="font-semibold">
                        {d.band} {d.score ? Math.round(d.score) : ""}
                      </dd>
                    </div>
                  </dl>
                  <p className="mt-2 text-[10px] text-ink-subtle">
                    Click to open this service
                  </p>
                </div>
              );
            }}
          />

          <Scatter
            data={data}
            fillOpacity={0.72}
            onClick={(entry) => {
              const point = entry as unknown as (typeof data)[number];
              if (point?.providerCode) {
                router.push(
                  `/service/${encodeURIComponent(
                    point.providerCode,
                  )}/${encodeURIComponent(point.specialtyCode)}`,
                );
              }
            }}
            style={{ cursor: "pointer" }}
            isAnimationActive={false}
          >
            {data.map((entry, index) => (
              <Cell
                key={index}
                fill={BAND_CHART_COLOURS[entry.band] ?? "#8494ad"}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        {Object.entries(BAND_CHART_COLOURS)
          .filter(([band]) => band !== "UNSCORED")
          .map(([band, colour]) => (
            <span key={band} className="flex items-center gap-1.5 text-2xs text-ink-muted">
              <span
                aria-hidden="true"
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: colour }}
              />
              {band.charAt(0) + band.slice(1).toLowerCase()}
            </span>
          ))}
        <span className="text-2xs text-ink-subtle">
          Bubble size = waiting-list size. Top-right = growing fastest with the
          heaviest long-wait burden.
        </span>
      </div>
    </div>
  );
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}
