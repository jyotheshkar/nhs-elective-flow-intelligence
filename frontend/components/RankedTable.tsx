"use client";

import Link from "next/link";

import PriorityBadge from "@/components/PriorityBadge";
import {
  TONE_CLASS,
  fmtCount,
  fmtDecimal,
  fmtPct,
  fmtScore,
  fmtSignedPct,
  isNum,
  movementGlyph,
  movementTone,
} from "@/lib/format";
import type { ServiceRow } from "@/types/api";

interface Column {
  key: string;
  label: string;
  sortable: boolean;
  align: "left" | "right";
  hideBelow?: string;
}

const COLUMNS: Column[] = [
  { key: "rank", label: "#", sortable: false, align: "left" },
  { key: "provider_name", label: "Provider", sortable: true, align: "left" },
  { key: "specialty_name", label: "Specialty", sortable: true, align: "left" },
  { key: "priority_score", label: "Priority", sortable: true, align: "right" },
  {
    key: "total_incomplete_pathways",
    label: "Waiting list",
    sortable: true,
    align: "right",
  },
  {
    key: "backlog_growth_3m_pct",
    label: "3M growth",
    sortable: true,
    align: "right",
  },
  {
    key: "pct_within_18_weeks",
    label: "Within 18w",
    sortable: true,
    align: "right",
  },
  {
    key: "pct_over_52_weeks",
    label: "52w+",
    sortable: true,
    align: "right",
    hideBelow: "lg",
  },
  {
    key: "forecast_change_3m_pct",
    label: "Forecast 3M",
    sortable: true,
    align: "right",
    hideBelow: "xl",
  },
  {
    key: "median_wait_weeks",
    label: "Median wait",
    sortable: true,
    align: "right",
    hideBelow: "xl",
  },
];

interface Props {
  rows: ServiceRow[];
  sortBy: string;
  descending: boolean;
  onSort: (column: string) => void;
  offset?: number;
  caption?: string;
}

export default function RankedTable({
  rows,
  sortBy,
  descending,
  onSort,
  offset = 0,
  caption,
}: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[880px] border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="table-head">
            {COLUMNS.map((column) => {
              const active = sortBy === column.key;
              const hide = column.hideBelow
                ? `hidden ${column.hideBelow}:table-cell`
                : "";
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={`whitespace-nowrap px-3 py-2.5 ${
                    column.align === "right" ? "text-right" : "text-left"
                  } ${hide}`}
                  aria-sort={
                    active
                      ? descending
                        ? "descending"
                        : "ascending"
                      : column.sortable
                        ? "none"
                        : undefined
                  }
                >
                  {column.sortable ? (
                    <button
                      type="button"
                      onClick={() => onSort(column.key)}
                      className={`inline-flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:text-ink ${
                        active ? "text-brand-800" : ""
                      }`}
                    >
                      {column.label}
                      <span aria-hidden="true" className="text-[9px]">
                        {active ? (descending ? "▼" : "▲") : "⇅"}
                      </span>
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              );
            })}
          </tr>
        </thead>

        <tbody className="divide-y divide-surface-border">
          {rows.map((row, index) => {
            const growthTone = movementTone(row.backlog_growth_3m_pct, false);
            const forecastTone = movementTone(row.forecast_change_3m_pct, false);
            return (
              <tr
                key={`${row.provider_code}-${row.specialty_code}`}
                className="transition-colors hover:bg-surface-subtle"
              >
                <td className="tnum whitespace-nowrap px-3 py-2.5 text-2xs text-ink-subtle">
                  {offset + index + 1}
                </td>

                <td className="max-w-[240px] px-3 py-2.5">
                  <Link
                    href={`/service/${encodeURIComponent(
                      row.provider_code,
                    )}/${encodeURIComponent(row.specialty_code)}`}
                    className="block truncate font-medium text-brand-700 hover:underline"
                    title={row.provider_name ?? row.provider_code}
                  >
                    {row.provider_short_name ?? row.provider_name ?? row.provider_code}
                  </Link>
                  <span className="block truncate text-2xs text-ink-subtle">
                    {row.region_name ?? ""}
                  </span>
                </td>

                <td className="max-w-[180px] truncate px-3 py-2.5 text-ink-muted">
                  {row.specialty_short_name ?? row.specialty_name}
                </td>

                <td className="whitespace-nowrap px-3 py-2.5 text-right">
                  <span className="inline-flex items-center justify-end gap-2">
                    <span className="tnum font-semibold text-ink">
                      {fmtScore(row.priority_score)}
                    </span>
                    <PriorityBadge band={row.priority_band} />
                  </span>
                </td>

                <td className="tnum whitespace-nowrap px-3 py-2.5 text-right font-medium text-ink">
                  {fmtCount(row.total_incomplete_pathways)}
                </td>

                <td
                  className={`tnum whitespace-nowrap px-3 py-2.5 text-right font-medium ${TONE_CLASS[growthTone]}`}
                >
                  <span aria-hidden="true" className="mr-0.5 text-[9px]">
                    {movementGlyph(row.backlog_growth_3m_pct)}
                  </span>
                  {fmtSignedPct(row.backlog_growth_3m_pct)}
                </td>

                <td className="tnum whitespace-nowrap px-3 py-2.5 text-right text-ink-muted">
                  {fmtPct(row.pct_within_18_weeks)}
                </td>

                <td className="tnum hidden whitespace-nowrap px-3 py-2.5 text-right text-ink-muted lg:table-cell">
                  {fmtPct(row.pct_over_52_weeks, 2)}
                </td>

                <td
                  className={`tnum hidden whitespace-nowrap px-3 py-2.5 text-right xl:table-cell ${
                    row.forecast_status === "ok"
                      ? TONE_CLASS[forecastTone]
                      : "text-ink-subtle"
                  }`}
                >
                  {row.forecast_status === "ok"
                    ? fmtSignedPct(row.forecast_change_3m_pct)
                    : "n/a"}
                </td>

                <td className="tnum hidden whitespace-nowrap px-3 py-2.5 text-right text-ink-muted xl:table-cell">
                  {isNum(row.median_wait_weeks)
                    ? `${fmtDecimal(row.median_wait_weeks)}w`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
