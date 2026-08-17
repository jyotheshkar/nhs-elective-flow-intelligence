"use client";

import { useCallback, useMemo, useState } from "react";

import FilterBar from "@/components/FilterBar";
import RankedTable from "@/components/RankedTable";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  WarehouseMissingState,
} from "@/components/States";
import { api, type DashboardFilters } from "@/lib/api";
import { useApiData } from "@/lib/useApiData";
import { useReferenceData } from "@/lib/useReferenceData";
import type { RankingsResponse } from "@/types/api";

const PAGE_SIZE = 50;

export default function RankingsPage() {
  const [filters, setFiltersState] = useState<DashboardFilters>({});
  const [sortBy, setSortByState] = useState("priority_score");
  const [descending, setDescending] = useState(true);
  const [offset, setOffset] = useState(0);
  const [rankableOnly, setRankableOnlyState] = useState(true);

  const reference = useReferenceData();

  // Any change to the result set resets pagination. Done in the event
  // handlers rather than an effect so there is no cascading render.
  const setFilters = useCallback((next: DashboardFilters) => {
    setFiltersState(next);
    setOffset(0);
  }, []);

  const setRankableOnly = useCallback((next: boolean) => {
    setRankableOnlyState(next);
    setOffset(0);
  }, []);

  const handleSort = useCallback(
    (column: string) => {
      setOffset(0);
      if (column === sortBy) {
        setDescending((value) => !value);
      } else {
        setSortByState(column);
        setDescending(true);
      }
    },
    [sortBy],
  );

  const queryKey = JSON.stringify({
    filters,
    sortBy,
    descending,
    offset,
    rankableOnly,
  });

  const fetcher = useCallback(
    (signal: AbortSignal) => {
      const query = JSON.parse(queryKey) as {
        filters: DashboardFilters;
        sortBy: string;
        descending: boolean;
        offset: number;
        rankableOnly: boolean;
      };
      return api.rankings(
        {
          ...query.filters,
          sort_by: query.sortBy,
          descending: query.descending,
          limit: PAGE_SIZE,
          offset: query.offset,
          rankable_only: query.rankableOnly,
        },
        signal,
      );
    },
    [queryKey],
  );

  const { data, error, loading, reload } = useApiData<RankingsResponse>(fetcher);

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

  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink sm:text-2xl">
            Service rankings
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Every provider and specialty, ranked and sortable. Export the
            filtered view for further analysis.
          </p>
        </div>
        <a href={exportUrl} className="btn btn-primary text-xs" download>
          ↓ Download filtered CSV
        </a>
      </header>

      <FilterBar
        providers={reference.data.providers}
        specialties={reference.data.specialties}
        regions={reference.data.regions}
        value={filters}
        onChange={setFilters}
        resultCount={total}
      />

      {failure && !data ? (
        <ErrorState
          title="Could not load rankings"
          message={failure.message}
          remedy={failure.remedy}
          onRetry={() => {
            reload();
            reference.reload();
          }}
        />
      ) : (
        <section className="card" aria-labelledby="table-heading">
          <div className="card-header">
            <div>
              <h2 id="table-heading" className="card-title">
                Ranked services
              </h2>
              <p className="card-subtitle">
                {total.toLocaleString("en-GB")} services · page {page} of {pages}
              </p>
            </div>
            <label className="flex items-center gap-2 text-xs text-ink-muted">
              <input
                type="checkbox"
                checked={rankableOnly}
                onChange={(e) => setRankableOnly(e.target.checked)}
                className="h-3.5 w-3.5 accent-brand-700"
              />
              Exclude services below the ranking threshold
            </label>
          </div>

          {loading && !data ? (
            <div className="p-5">
              <CardSkeleton height="h-96" />
            </div>
          ) : total === 0 ? (
            <div className="p-5">
              <EmptyState
                title="No services match these filters"
                message="Try widening the selection, clearing the search term, or including services below the ranking threshold."
                action={
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setFilters({})}
                  >
                    Reset filters
                  </button>
                }
              />
            </div>
          ) : (
            <>
              <RankedTable
                rows={data?.rows ?? []}
                sortBy={sortBy}
                descending={descending}
                onSort={handleSort}
                offset={offset}
                caption="All provider and specialty services ranked by operational priority score"
              />

              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-surface-border px-5 py-3">
                <p className="text-xs text-ink-subtle" aria-live="polite">
                  Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of{" "}
                  {total.toLocaleString("en-GB")}
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="btn text-xs"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    ← Previous
                  </button>
                  <button
                    type="button"
                    className="btn text-xs"
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    Next →
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  );
}
