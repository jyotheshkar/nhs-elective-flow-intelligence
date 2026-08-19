"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import AttentionCards from "@/components/AttentionCards";
import FilterBar from "@/components/FilterBar";
import KpiRow from "@/components/KpiRow";
import RankedTable from "@/components/RankedTable";
import PriorityMatrix from "@/components/charts/PriorityMatrix";
import WaitingListTrendChart from "@/components/charts/WaitingListTrendChart";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  WarehouseMissingState,
} from "@/components/States";
import { api, type DashboardFilters } from "@/lib/api";
import { useApiData } from "@/lib/useApiData";
import { useReferenceData } from "@/lib/useReferenceData";
import type { OverviewResponse, RankingsResponse } from "@/types/api";

interface DashboardPayload {
  overview: OverviewResponse;
  rankings: RankingsResponse;
}

export default function ControlRoomPage() {
  const [filters, setFilters] = useState<DashboardFilters>({});
  const [sortBy, setSortBy] = useState("priority_score");
  const [descending, setDescending] = useState(true);

  const reference = useReferenceData();

  // Serialised so the fetcher identity changes exactly when a query input
  // changes — this is the cache key for useApiData.
  const queryKey = JSON.stringify({ filters, sortBy, descending });
  const fetcher = useCallback(
    async (signal: AbortSignal) => {
      const { filters: f, sortBy: s, descending: d } = JSON.parse(queryKey) as {
        filters: DashboardFilters;
        sortBy: string;
        descending: boolean;
      };
      const [overview, rankings] = await Promise.all([
        api.overview(f, signal),
        api.rankings({ ...f, sort_by: s, descending: d, limit: 25 }, signal),
      ]);
      return { overview, rankings } satisfies DashboardPayload;
    },
    [queryKey],
  );

  const { data, error, loading, reload } = useApiData<DashboardPayload>(fetcher);

  const handleSort = useCallback(
    (column: string) => {
      if (column === sortBy) {
        setDescending((value) => !value);
      } else {
        setSortBy(column);
        setDescending(true);
      }
    },
    [sortBy],
  );

  const exportUrl = useMemo(
    () => api.rankingsExportUrl({ ...filters, sort_by: sortBy, descending }),
    [filters, sortBy, descending],
  );

  const failure = error ?? reference.error;

  if (failure?.isWarehouseMissing) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <WarehouseMissingState message={failure.message} />
      </div>
    );
  }

  if (failure && !data) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <ErrorState
          title="Could not load the control room"
          message={failure.message}
          remedy={failure.remedy}
          onRetry={() => {
            reload();
            reference.reload();
          }}
        />
      </div>
    );
  }

  const overview = data?.overview ?? null;
  const rankings = data?.rankings ?? null;
  const provenance = overview?.provenance;
  const hasResults = (rankings?.total ?? 0) > 0;
  const firstLoad = loading && !data;

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 sm:px-6">
      {/* --- Page header ------------------------------------------------ */}
      <header>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="label text-brand-700">
              Operational decision intelligence
            </p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink sm:text-3xl">
              Elective Flow Control Room
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              Identify pressure. Understand trajectory. Test interventions.
            </p>
          </div>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
            <div>
              <dt className="label">Latest data</dt>
              <dd className="mt-0.5 font-semibold text-ink-muted">
                {provenance?.latest_reporting_month_label ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="label">Source</dt>
              <dd className="mt-0.5 font-semibold text-ink-muted">
                {provenance?.is_demo ? "Synthetic demo data" : "NHS England"}
              </dd>
            </div>
            <div>
              <dt className="label">Periods loaded</dt>
              <dd className="mt-0.5 font-semibold text-ink-muted">
                {provenance?.reporting_months ?? 0} months
              </dd>
            </div>
          </dl>
        </div>
      </header>

      <FilterBar
        providers={reference.data.providers}
        specialties={reference.data.specialties}
        regions={reference.data.regions}
        value={filters}
        onChange={setFilters}
        resultCount={rankings?.total}
      />

      {/* --- KPI row ----------------------------------------------------- */}
      {firstLoad ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="card p-4">
              <div className="skeleton h-3 w-2/3" />
              <div className="skeleton mt-3 h-7 w-1/2" />
              <div className="skeleton mt-2 h-3 w-3/4" />
            </div>
          ))}
        </div>
      ) : overview && overview.kpis.length > 0 ? (
        <KpiRow kpis={overview.kpis} />
      ) : null}

      {!loading && overview && overview.kpis.length === 0 && (
        <EmptyState
          title="No services match these filters"
          message="Try widening the region, provider or specialty selection, or clear the search term."
          action={
            <button type="button" className="btn" onClick={() => setFilters({})}>
              Reset filters
            </button>
          }
        />
      )}

      {hasResults && overview && (
        <>
          {/* --- Attention + trend --------------------------------------- */}
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
            <section
              className="card xl:col-span-5"
              aria-labelledby="attention-heading"
            >
              <div className="card-header">
                <div>
                  <h2 id="attention-heading" className="card-title">
                    Where should operational attention go first?
                  </h2>
                  <p className="card-subtitle">
                    Highest priority services in the current selection
                  </p>
                </div>
                <Link href="/rankings" className="btn btn-ghost text-xs">
                  View all →
                </Link>
              </div>
              <AttentionCards cards={overview.attention} />
            </section>

            <section className="card xl:col-span-7" aria-labelledby="trend-heading">
              <div className="card-header">
                <div>
                  <h2 id="trend-heading" className="card-title">
                    Waiting list trend
                  </h2>
                  <p className="card-subtitle">
                    {overview.trend_scope === "filtered"
                      ? "Aggregated across the filtered selection"
                      : Object.keys(overview.filters_applied).length > 0
                        ? "All loaded providers and specialties — the selection is too broad to aggregate as a series"
                        : "All loaded providers and specialties"}
                  </p>
                </div>
              </div>
              <div className="p-5">
                <WaitingListTrendChart
                  history={overview.national_trend}
                  height={280}
                />
              </div>
            </section>
          </div>

          {/* --- Priority matrix ----------------------------------------- */}
          <section className="card" aria-labelledby="matrix-heading">
            <div className="card-header">
              <div>
                <h2 id="matrix-heading" className="card-title">
                  Priority matrix
                </h2>
                <p className="card-subtitle">
                  Waiting-list growth against long-wait burden. Select a point to
                  open that service.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(overview.band_counts).map(([band, count]) => (
                  <span
                    key={band}
                    className="rounded-full border border-surface-border bg-surface-muted px-2.5 py-1 text-2xs font-medium text-ink-muted"
                  >
                    {band.charAt(0) + band.slice(1).toLowerCase()}:{" "}
                    <span className="tnum font-bold">{count}</span>
                  </span>
                ))}
              </div>
            </div>
            <div className="p-5">
              <PriorityMatrix points={overview.matrix} />
            </div>
          </section>

          {/* --- Ranked table -------------------------------------------- */}
          <section className="card" aria-labelledby="rankings-heading">
            <div className="card-header">
              <div>
                <h2 id="rankings-heading" className="card-title">
                  Highest priority services
                </h2>
                <p className="card-subtitle">
                  Showing {rankings?.returned ?? 0} of{" "}
                  {(rankings?.total ?? 0).toLocaleString("en-GB")} ranked services
                </p>
              </div>
              <div className="flex gap-2">
                <a href={exportUrl} className="btn text-xs" download>
                  ↓ Download CSV
                </a>
                <Link href="/rankings" className="btn btn-ghost text-xs">
                  Full table →
                </Link>
              </div>
            </div>
            <RankedTable
              rows={rankings?.rows ?? []}
              sortBy={sortBy}
              descending={descending}
              onSort={handleSort}
              caption="Provider and specialty services ranked by operational priority score"
            />
          </section>
        </>
      )}

      {firstLoad && (
        <>
          <CardSkeleton height="h-64" />
          <CardSkeleton height="h-72" />
        </>
      )}

      {!loading && !hasResults && overview && overview.kpis.length > 0 && (
        <EmptyState
          title="No rankable services in this selection"
          message="Services below the ranking threshold are scored but excluded from headline rankings, because small waiting lists produce unstable growth rates."
        />
      )}
    </div>
  );
}
