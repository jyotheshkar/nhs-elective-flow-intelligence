"use client";

import { useEffect, useState } from "react";

import type { DashboardFilters } from "@/lib/api";
import type { Provider, Region, Specialty } from "@/types/api";

interface Props {
  providers: Provider[];
  specialties: Specialty[];
  regions: Region[];
  value: DashboardFilters;
  onChange: (filters: DashboardFilters) => void;
  resultCount?: number;
}

const BANDS = ["CRITICAL", "HIGH", "MODERATE", "LOW"];

export default function FilterBar({
  providers,
  specialties,
  regions,
  value,
  onChange,
  resultCount,
}: Props) {
  // Search is debounced locally so each keystroke does not fire a request.
  const [search, setSearch] = useState(value.search ?? "");
  const [syncedSearch, setSyncedSearch] = useState(value.search ?? "");

  // Adjust local state when the parent resets filters externally. Setting
  // state during render (rather than in an effect) is React's documented
  // pattern for this and avoids a cascading second render.
  const externalSearch = value.search ?? "";
  if (externalSearch !== syncedSearch) {
    setSyncedSearch(externalSearch);
    setSearch(externalSearch);
  }

  useEffect(() => {
    // Already in sync — nothing to push, and this is the terminating case
    // after the parent accepts a debounced update.
    if ((value.search ?? "") === search) return;
    const timer = setTimeout(() => {
      onChange({ ...value, search: search || undefined });
    }, 300);
    return () => clearTimeout(timer);
  }, [search, value, onChange]);

  const activeCount = Object.entries(value).filter(
    ([, v]) => v !== undefined && v !== "",
  ).length;

  function set(key: keyof DashboardFilters, next: string) {
    onChange({ ...value, [key]: next || undefined });
  }

  // Providers narrow to the selected region so the list stays navigable.
  const visibleProviders = value.region
    ? providers.filter(
        (p) => p.region_name === value.region || p.region_code === value.region,
      )
    : providers;

  return (
    <section
      aria-label="Dashboard filters"
      className="card no-print px-4 py-3"
    >
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div>
          <label htmlFor="filter-region" className="label mb-1 block">
            Region
          </label>
          <select
            id="filter-region"
            className="control"
            value={value.region ?? ""}
            onChange={(e) => {
              // Changing region invalidates a provider outside it.
              onChange({
                ...value,
                region: e.target.value || undefined,
                provider_code: undefined,
              });
            }}
          >
            <option value="">All regions</option>
            {regions.map((region) => (
              <option key={region.region_code} value={region.region_name}>
                {region.region_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="filter-provider" className="label mb-1 block">
            Provider
          </label>
          <select
            id="filter-provider"
            className="control"
            value={value.provider_code ?? ""}
            onChange={(e) => set("provider_code", e.target.value)}
          >
            <option value="">All providers ({visibleProviders.length})</option>
            {visibleProviders.map((provider) => (
              <option key={provider.provider_code} value={provider.provider_code}>
                {provider.provider_short_name ?? provider.provider_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="filter-specialty" className="label mb-1 block">
            Specialty
          </label>
          <select
            id="filter-specialty"
            className="control"
            value={value.specialty_code ?? ""}
            onChange={(e) => set("specialty_code", e.target.value)}
          >
            <option value="">All specialties</option>
            {specialties.map((specialty) => (
              <option
                key={specialty.specialty_code}
                value={specialty.specialty_code}
              >
                {specialty.specialty_short_name ?? specialty.specialty_name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="filter-band" className="label mb-1 block">
            Priority band
          </label>
          <select
            id="filter-band"
            className="control"
            value={value.priority_band ?? ""}
            onChange={(e) => set("priority_band", e.target.value)}
          >
            <option value="">All bands</option>
            {BANDS.map((band) => (
              <option key={band} value={band}>
                {band.charAt(0) + band.slice(1).toLowerCase()}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="filter-search" className="label mb-1 block">
            Search
          </label>
          <input
            id="filter-search"
            type="search"
            className="control"
            placeholder="Provider or specialty…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-surface-border pt-3">
        <p className="text-xs text-ink-subtle" aria-live="polite">
          {typeof resultCount === "number" && (
            <>
              <span className="tnum font-semibold text-ink-muted">
                {resultCount.toLocaleString("en-GB")}
              </span>{" "}
              services match
            </>
          )}
          {activeCount > 0 && (
            <span className="ml-2">
              · {activeCount} filter{activeCount === 1 ? "" : "s"} applied
            </span>
          )}
        </p>
        <button
          type="button"
          className="btn btn-ghost text-xs"
          onClick={() => {
            setSearch("");
            onChange({});
          }}
          disabled={activeCount === 0}
        >
          Reset filters
        </button>
      </div>
    </section>
  );
}
