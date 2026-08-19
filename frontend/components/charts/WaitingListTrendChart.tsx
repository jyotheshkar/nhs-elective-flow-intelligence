"use client";

import {
  Area,
  ComposedChart,
  CartesianGrid,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtCompact, fmtCount, fmtMonth } from "@/lib/format";
import type { TimeseriesPoint } from "@/types/api";

interface Props {
  history: TimeseriesPoint[];
  forecast?: TimeseriesPoint[];
  height?: number;
}

interface ChartRow {
  month: string;
  label: string;
  actual: number | null;
  forecast: number | null;
  band: [number, number] | null;
}

/**
 * Waiting-list history with the forecast overlaid.
 *
 * Historical and forecast values are separate series so the visual break is
 * unambiguous: a solid line for what happened, a dashed line and a shaded
 * interval for what is modelled. The last actual point is duplicated into the
 * forecast series so the two lines join without implying the forecast starts
 * from a different level.
 */
export default function WaitingListTrendChart({
  history,
  forecast = [],
  height = 300,
}: Props) {
  const rows: ChartRow[] = history.map((point) => ({
    month: point.month_key,
    label: point.month_label ?? fmtMonth(point.month_key),
    actual: point.waiting_list ?? null,
    forecast: null,
    band: null,
  }));

  if (forecast.length > 0 && rows.length > 0) {
    const last = rows[rows.length - 1];
    last.forecast = last.actual;
    last.band = last.actual !== null ? [last.actual, last.actual] : null;

    for (const point of forecast) {
      rows.push({
        month: point.month_key,
        label: point.month_label ?? fmtMonth(point.month_key),
        actual: null,
        forecast: point.waiting_list ?? null,
        band:
          typeof point.forecast_lower === "number" &&
          typeof point.forecast_upper === "number"
            ? [point.forecast_lower, point.forecast_upper]
            : null,
      });
    }
  }

  const forecastStart =
    forecast.length > 0 && history.length > 0
      ? history[history.length - 1].month_key
      : null;

  if (rows.length === 0) {
    return (
      <p className="py-12 text-center text-sm text-ink-subtle">
        No history available for this selection.
      </p>
    );
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#dbe3ef" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: "#5f6b82" }}
            tickLine={false}
            axisLine={{ stroke: "#dbe3ef" }}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "#5f6b82" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => fmtCompact(value as number)}
            width={52}
          />
          <Tooltip
            formatter={(value, name) => {
              if (name === "Modelled range") {
                const range = value as unknown as [number, number];
                return [
                  `${fmtCount(range[0])} – ${fmtCount(range[1])}`,
                  "Modelled range (80%)",
                ];
              }
              return [fmtCount(value as number), name as string];
            }}
            contentStyle={{
              fontSize: 12,
              borderRadius: 8,
              border: "1px solid #dbe3ef",
              boxShadow: "0 4px 6px -1px rgb(15 23 42 / 0.07)",
            }}
          />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            iconType="plainline"
          />

          <Area
            dataKey="band"
            name="Modelled range"
            stroke="none"
            fill="#0072ce"
            fillOpacity={0.1}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="actual"
            name="Waiting list (published)"
            stroke="#003087"
            strokeWidth={2.25}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="forecast"
            name="Forecast (modelled)"
            stroke="#0072ce"
            strokeWidth={2.25}
            strokeDasharray="5 4"
            dot={{ r: 3, fill: "#0072ce" }}
            connectNulls
            isAnimationActive={false}
          />

          {forecastStart && (
            <ReferenceLine
              x={fmtMonth(forecastStart)}
              stroke="#8494ad"
              strokeDasharray="2 3"
              label={{
                value: "Forecast →",
                position: "insideTopRight",
                fontSize: 10,
                fill: "#5f6b82",
              }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <p className="mt-2 text-2xs leading-relaxed text-ink-subtle">
        Solid line: published NHS England waiting-list counts. Dashed line and
        shaded band: modelled forecast with an indicative 80% range. Forecasts
        extrapolate recent behaviour and are not predictions of outcome.
      </p>
    </div>
  );
}
