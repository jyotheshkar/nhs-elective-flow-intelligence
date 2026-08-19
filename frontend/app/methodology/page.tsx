"use client";

import { useCallback } from "react";

import { CardSkeleton, ErrorState } from "@/components/States";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";
import type { MethodologyResponse } from "@/types/api";

export default function MethodologyPage() {
  const fetcher = useCallback(
    (signal: AbortSignal) => api.methodology(signal),
    [],
  );
  const { data, error, reload } = useApiData<MethodologyResponse>(fetcher);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <ErrorState
          title="Could not load the methodology"
          message={error.message}
          remedy={error.remedy}
          onRetry={reload}
        />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="mx-auto max-w-4xl space-y-4 px-4 py-8 sm:px-6">
        <CardSkeleton height="h-40" />
        <CardSkeleton height="h-40" />
      </div>
    );
  }

  const forecast = data.forecast_summary as Record<string, number | null>;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <header className="mb-8">
        <p className="label text-brand-700">Methodology</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight text-ink">
          How it works
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ink-muted">
          Every number in this product is traceable to a published NHS England
          statistic or to a formula documented on this page. Nothing is
          hardcoded and nothing is inferred beyond what the source supports.
        </p>
      </header>

      {/* --- Contents --------------------------------------------------- */}
      <nav aria-label="Methodology contents" className="card mb-8 p-4">
        <p className="label mb-2">On this page</p>
        <ol className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
          {data.sections.map((section) => (
            <li key={section.key}>
              <a
                href={`#${section.key}`}
                className="text-xs text-brand-700 hover:underline"
              >
                {section.title}
              </a>
            </li>
          ))}
          <li>
            <a href="#limitations" className="text-xs text-brand-700 hover:underline">
              10. Limitations
            </a>
          </li>
        </ol>
      </nav>

      {/* --- Priority score summary ------------------------------------- */}
      <section className="card mb-6 p-5" aria-labelledby="score-summary">
        <h2 id="score-summary" className="card-title mb-3">
          Priority score at a glance
        </h2>
        <ul className="space-y-2">
          {data.priority_components.map((component) => (
            <li key={component.key} className="flex items-start gap-3">
              <span className="tnum w-12 shrink-0 rounded bg-brand-50 px-2 py-1 text-center text-xs font-bold text-brand-800">
                {component.weight}%
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-medium text-ink">
                  {component.label}
                </span>
                <span className="block text-xs leading-relaxed text-ink-muted">
                  {component.description}
                </span>
              </span>
            </li>
          ))}
        </ul>

        <div className="mt-4 flex flex-wrap gap-2 border-t border-surface-border pt-4">
          {data.priority_bands.map((band) => (
            <span
              key={band.band}
              className="rounded-full border border-surface-border bg-surface-muted px-3 py-1 text-2xs font-semibold text-ink-muted"
            >
              {band.band}: {band.min_score}–{band.max_score}
            </span>
          ))}
        </div>
      </section>

      {/* --- Forecast performance --------------------------------------- */}
      <section className="card mb-6 p-5" aria-labelledby="forecast-perf">
        <h2 id="forecast-perf" className="card-title mb-1">
          Forecast performance on the loaded data
        </h2>
        <p className="mb-4 text-xs text-ink-muted">
          Measured by rolling-origin backtesting. Reported as observed, including
          where the models do not beat a naive benchmark.
        </p>
        <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="label">Series forecast</dt>
            <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
              {forecast.series_ok?.toLocaleString("en-GB") ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="label">Insufficient history</dt>
            <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
              {forecast.series_insufficient?.toLocaleString("en-GB") ?? "—"}
            </dd>
          </div>
          <div>
            <dt className="label">Median MAPE</dt>
            <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
              {forecast.median_mape != null ? `${forecast.median_mape}%` : "—"}
            </dd>
          </div>
          <div>
            <dt className="label">Beating naive</dt>
            <dd className="tnum mt-0.5 text-lg font-semibold text-ink">
              {forecast.share_beating_naive != null
                ? `${forecast.share_beating_naive}%`
                : "—"}
            </dd>
          </div>
        </dl>
      </section>

      {/* --- Sections ---------------------------------------------------- */}
      <div className="space-y-5">
        {data.sections.map((section) => (
          <section
            key={section.key}
            id={section.key}
            className="card p-5 scroll-mt-24"
            aria-labelledby={`${section.key}-heading`}
          >
            <h2
              id={`${section.key}-heading`}
              className="text-base font-semibold tracking-tight text-ink"
            >
              {section.title}
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-muted">
              {section.body}
            </p>

            {section.formula && (
              <pre className="mt-3 overflow-x-auto rounded-md border border-surface-border bg-surface-subtle p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
                {section.formula}
              </pre>
            )}

            {section.bullets.length > 0 && (
              <ul className="mt-3 space-y-1.5">
                {section.bullets.map((bullet) => (
                  <li
                    key={bullet}
                    className="flex gap-2 text-xs leading-relaxed text-ink-muted"
                  >
                    <span aria-hidden="true" className="text-brand-600">
                      ·
                    </span>
                    <span>{bullet}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}

        {/* --- Limitations ---------------------------------------------- */}
        <section
          id="limitations"
          className="card scroll-mt-24 border-band-moderateBorder p-5"
          aria-labelledby="limitations-heading"
        >
          <h2
            id="limitations-heading"
            className="text-base font-semibold tracking-tight text-ink"
          >
            10. Limitations
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-muted">
            These constraints are material to how the output should be read.
            They are stated here rather than buried, because a decision-support
            tool that overstates its own confidence is worse than no tool.
          </p>
          <ul className="mt-3 space-y-2">
            {data.limitations.map((limitation) => (
              <li
                key={limitation}
                className="flex gap-2 text-xs leading-relaxed text-ink-muted"
              >
                <span aria-hidden="true" className="text-band-moderate">
                  !
                </span>
                <span>{limitation}</span>
              </li>
            ))}
          </ul>
        </section>

        {/* --- Provenance ------------------------------------------------ */}
        <section className="card p-5" aria-labelledby="provenance-heading">
          <h2
            id="provenance-heading"
            className="text-base font-semibold tracking-tight text-ink"
          >
            11. This build
          </h2>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Row label="Data source type" value={data.provenance.data_source_type} />
            <Row label="Source" value={data.provenance.source_name} />
            <Row
              label="Reporting periods"
              value={`${data.provenance.reporting_months} months (${
                data.provenance.earliest_reporting_month ?? "—"
              } to ${data.provenance.latest_reporting_month ?? "—"})`}
            />
            <Row
              label="Source files ingested"
              value={String(data.provenance.source_files)}
            />
            <Row
              label="Publication date"
              value={data.provenance.published_date ?? "—"}
            />
            <Row label="Retrieved" value={fmtDate(data.provenance.retrieved_at)} />
            <Row label="Warehouse built" value={fmtDate(data.provenance.built_at)} />
            <Row label="Licence" value={data.provenance.licence ?? "—"} />
          </dl>
          {data.provenance.source_landing_page && (
            <a
              href={data.provenance.source_landing_page}
              target="_blank"
              rel="noreferrer"
              className="mt-4 inline-block text-xs text-brand-700 hover:underline"
            >
              View the NHS England RTT publication ↗
            </a>
          )}
        </section>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mt-0.5 break-words text-xs font-medium text-ink-muted">
        {value}
      </dd>
    </div>
  );
}
