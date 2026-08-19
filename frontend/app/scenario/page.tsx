"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import PriorityBadge from "@/components/PriorityBadge";
import ScenarioSimulator from "@/components/ScenarioSimulator";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  WarehouseMissingState,
} from "@/components/States";
import { api } from "@/lib/api";
import { fmtCount, fmtPct, fmtSignedPct } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";
import { useReferenceData } from "@/lib/useReferenceData";
import type { ProviderDetailResponse, ServiceRow } from "@/types/api";

/**
 * Standalone scenario analysis.
 *
 * The simulator also lives on each service detail page; this page makes it a
 * first-class destination with its own provider and specialty selection, so a
 * user can test activity scenarios without first finding a service through
 * the rankings.
 */
export default function ScenarioPage() {
  const reference = useReferenceData();
  const { providers } = reference.data;

  const [providerChoice, setProviderChoice] = useState<string | null>(null);
  const providerCode = providerChoice ?? providers[0]?.provider_code ?? "";

  // The specialty dropdown is populated from the services this provider
  // actually reports, ordered by priority, so the user is never offered a
  // provider x specialty pair with no data behind it.
  const detailFetcher = useCallback(
    async (signal: AbortSignal): Promise<ProviderDetailResponse | null> => {
      if (!providerCode) return null;
      return api.providerDetail(providerCode, signal);
    },
    [providerCode],
  );
  const detail = useApiData<ProviderDetailResponse | null>(detailFetcher);

  const services: ServiceRow[] = useMemo(
    () => detail.data?.services ?? [],
    [detail.data],
  );

  const [specialtyChoice, setSpecialtyChoice] = useState<string | null>(null);
  // Fall back to the provider's top-priority service when no valid choice is
  // held (first load, or after switching provider).
  const validChoice = services.some(
    (s) => s.specialty_code === specialtyChoice,
  );
  const specialtyCode = validChoice
    ? (specialtyChoice as string)
    : (services[0]?.specialty_code ?? "");

  const selected = services.find((s) => s.specialty_code === specialtyCode);

  const failure = reference.error ?? detail.error;

  if (failure?.isWarehouseMissing) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <WarehouseMissingState message={failure.message} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1200px] space-y-5 px-4 py-6 sm:px-6">
      <header>
        <p className="label text-brand-700">What-if analysis</p>
        <h1 className="mt-1 text-xl font-bold tracking-tight text-ink sm:text-2xl">
          Scenario analysis
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-ink-muted">
          Test what the modelled waiting list would look like if a service
          completed more activity each month. An illustrative accounting
          projection under stated assumptions — not a causal prediction.
        </p>
      </header>

      {/* --- Service selection ------------------------------------------- */}
      <section className="card p-4" aria-labelledby="scenario-selection">
        <h2 id="scenario-selection" className="sr-only">
          Service selection
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="scenario-provider" className="label mb-1 block">
              Provider
            </label>
            <select
              id="scenario-provider"
              className="control"
              value={providerCode}
              onChange={(e) => {
                setProviderChoice(e.target.value);
                setSpecialtyChoice(null);
              }}
            >
              {providers.map((p) => (
                <option key={p.provider_code} value={p.provider_code}>
                  {p.provider_short_name ?? p.provider_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="scenario-specialty" className="label mb-1 block">
              Specialty (ordered by priority at this provider)
            </label>
            <select
              id="scenario-specialty"
              className="control"
              value={specialtyCode}
              onChange={(e) => setSpecialtyChoice(e.target.value)}
              disabled={services.length === 0}
            >
              {services.map((s) => (
                <option key={s.specialty_code} value={s.specialty_code}>
                  {(s.specialty_short_name ?? s.specialty_name) +
                    (s.priority_band && s.priority_band !== "UNSCORED"
                      ? " — " + s.priority_band
                      : "")}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>

      {failure && !detail.data && (
        <ErrorState
          title="Could not load provider services"
          message={failure.message}
          remedy={failure.remedy}
          onRetry={() => {
            detail.reload();
            reference.reload();
          }}
        />
      )}

      {detail.loading && !detail.data && <CardSkeleton height="h-48" />}

      {selected && (
        <>
          {/* --- Current position ------------------------------------- */}
          <section className="card" aria-labelledby="scenario-context-heading">
            <div className="card-header">
              <div>
                <h2 id="scenario-context-heading" className="card-title">
                  {selected.specialty_name}
                </h2>
                <p className="card-subtitle">
                  {selected.provider_name}
                  {selected.region_name ? ` · ${selected.region_name}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <PriorityBadge
                  band={selected.priority_band}
                  score={selected.priority_score}
                  showScore
                />
                <Link
                  href={`/service/${encodeURIComponent(
                    selected.provider_code,
                  )}/${encodeURIComponent(selected.specialty_code)}`}
                  className="btn btn-ghost text-xs"
                >
                  Full service detail →
                </Link>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-4 px-5 py-4 sm:grid-cols-4">
              <div>
                <dt className="label">Current waiting list</dt>
                <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
                  {fmtCount(selected.total_incomplete_pathways)}
                </dd>
              </div>
              <div>
                <dt className="label">3-month growth</dt>
                <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
                  {fmtSignedPct(selected.backlog_growth_3m_pct)}
                </dd>
              </div>
              <div>
                <dt className="label">Within 18 weeks</dt>
                <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
                  {fmtPct(selected.pct_within_18_weeks)}
                </dd>
              </div>
              <div>
                <dt className="label">Forecast (3 months)</dt>
                <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
                  {selected.forecast_status === "ok"
                    ? fmtCount(selected.forecast_3m)
                    : "Insufficient history"}
                </dd>
              </div>
            </dl>
          </section>

          {/* --- Simulator --------------------------------------------- */}
          <section className="card" aria-labelledby="scenario-sim-heading">
            <div className="card-header">
              <div>
                <h2 id="scenario-sim-heading" className="card-title">
                  Activity uplift simulator
                </h2>
                <p className="card-subtitle">
                  Modelled estimates only. Assumptions are listed below the
                  results.
                </p>
              </div>
            </div>
            <div className="p-5">
              <ScenarioSimulator
                key={`${selected.provider_code}-${selected.specialty_code}`}
                providerCode={selected.provider_code}
                specialtyCode={selected.specialty_code}
              />
            </div>
          </section>
        </>
      )}

      {!detail.loading && detail.data && services.length === 0 && (
        <EmptyState
          title="No services reported by this provider"
          message="Choose a different provider to run a scenario."
        />
      )}
    </div>
  );
}
