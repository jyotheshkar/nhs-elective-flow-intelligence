"use client";

import { useCallback, useState } from "react";

import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  WarehouseMissingState,
} from "@/components/States";
import { api } from "@/lib/api";
import { fmtCount, fmtDecimal, fmtMonth } from "@/lib/format";
import { useApiData } from "@/lib/useApiData";
import type { DataQualityResponse } from "@/types/api";

const SEVERITY_STYLES: Record<string, string> = {
  High: "bg-band-criticalBg text-band-critical border-band-criticalBorder",
  Medium: "bg-band-moderateBg text-band-moderate border-band-moderateBorder",
  Low: "bg-surface-muted text-ink-muted border-surface-border",
};

export default function DataQualityPage() {
  const [severity, setSeverity] = useState("");
  const [issueType, setIssueType] = useState("");

  const fetcher = useCallback(
    (signal: AbortSignal) =>
      api.dataQuality(
        {
          severity: severity || undefined,
          issue_type: issueType || undefined,
          limit: 300,
        },
        signal,
      ),
    [severity, issueType],
  );

  const { data, error, loading, reload } =
    useApiData<DataQualityResponse>(fetcher);

  if (error?.isWarehouseMissing) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <WarehouseMissingState message={error.message} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
        <ErrorState
          title="Could not load the data quality monitor"
          message={error.message}
          remedy={error.remedy}
          onRetry={reload}
        />
      </div>
    );
  }

  const metrics = (data?.metrics ?? {}) as Record<string, number | string>;

  return (
    <div className="mx-auto max-w-[1600px] space-y-5 px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="label text-brand-700">Governance</p>
          <h1 className="mt-1 text-xl font-bold tracking-tight text-ink sm:text-2xl">
            Data quality monitor
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-muted">
            Automated checks over the ingested NHS England statistics. Findings
            are items <em>requiring review</em>, not assertions that the
            published data is wrong — public statistics contain legitimate
            reporting changes and organisational mergers that an automated check
            cannot distinguish from a data problem.
          </p>
        </div>
        {data && (
          <div className="text-right">
            <p className="label">Overall score</p>
            <p className="tnum text-3xl font-bold leading-none text-ink">
              {fmtDecimal(data.overall_score, 1)}
              <span className="text-base font-normal text-ink-subtle"> / 100</span>
            </p>
          </div>
        )}
      </header>

      {loading && !data ? (
        <CardSkeleton height="h-40" />
      ) : (
        data && (
          <>
            {/* --- Dimensions --------------------------------------- */}
            <section aria-labelledby="dimensions-heading">
              <h2 id="dimensions-heading" className="sr-only">
                Quality dimensions
              </h2>
              <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {data.dimensions.map((dimension) => (
                  <li key={dimension.key} className="card p-4">
                    <div className="flex items-baseline justify-between gap-2">
                      <h3 className="label">{dimension.label}</h3>
                      <span className="text-2xs text-ink-subtle">
                        weight {dimension.weight}%
                      </span>
                    </div>
                    <p className="tnum mt-1.5 text-2xl font-semibold text-ink">
                      {fmtDecimal(dimension.score, 1)}
                      <span className="text-sm font-normal text-ink-subtle">
                        {" "}
                        / 100
                      </span>
                    </p>
                    <div
                      className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-muted"
                      role="img"
                      aria-label={`${dimension.label} scores ${dimension.score} out of 100`}
                    >
                      <div
                        className="h-full rounded-full bg-brand-600"
                        style={{ width: `${Math.min(dimension.score, 100)}%` }}
                      />
                    </div>
                    <p className="mt-2 text-2xs leading-relaxed text-ink-subtle">
                      {dimension.description}
                    </p>
                    <p className="mt-1.5 text-2xs font-medium text-ink-muted">
                      Contributes {fmtDecimal(dimension.contribution, 1)} points
                    </p>
                  </li>
                ))}
              </ul>
            </section>

            {/* --- Supporting metrics ------------------------------- */}
            <section className="card p-5" aria-labelledby="metrics-heading">
              <h2 id="metrics-heading" className="card-title mb-3">
                Underlying measurements
              </h2>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                <Metric
                  label="Reporting months"
                  value={String(metrics.reporting_months ?? "—")}
                />
                <Metric
                  label="Series tracked"
                  value={fmtCount(metrics.series_count as number)}
                />
                <Metric
                  label="Latest period"
                  value={fmtMonth(metrics.latest_month as string)}
                />
                <Metric
                  label="Publication lag"
                  value={`${metrics.lag_months ?? "—"} months`}
                />
                <Metric
                  label="Integrity checks run"
                  value={fmtCount(metrics.checks_run as number)}
                />
                <Metric
                  label="Anomalies flagged"
                  value={`${metrics.anomaly_count ?? 0} (${fmtDecimal(
                    metrics.anomaly_rate_pct as number,
                    2,
                  )}%)`}
                />
              </dl>
            </section>

            {/* --- Issue register ----------------------------------- */}
            <section className="card" aria-labelledby="issues-heading">
              <div className="card-header">
                <div>
                  <h2 id="issues-heading" className="card-title">
                    Issue register
                  </h2>
                  <p className="card-subtitle">
                    {data.total_issues.toLocaleString("en-GB")} findings across
                    the loaded periods · showing {data.returned_issues}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <div>
                    <label htmlFor="q-severity" className="sr-only">
                      Filter by severity
                    </label>
                    <select
                      id="q-severity"
                      className="control h-8 w-auto text-xs"
                      value={severity}
                      onChange={(e) => setSeverity(e.target.value)}
                    >
                      <option value="">All severities</option>
                      {Object.entries(data.severity_counts).map(([key, count]) => (
                        <option key={key} value={key}>
                          {key} ({count})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="q-type" className="sr-only">
                      Filter by issue type
                    </label>
                    <select
                      id="q-type"
                      className="control h-8 w-auto text-xs"
                      value={issueType}
                      onChange={(e) => setIssueType(e.target.value)}
                    >
                      <option value="">All issue types</option>
                      {Object.entries(data.issue_type_counts).map(([key, count]) => (
                        <option key={key} value={key}>
                          {key} ({count})
                        </option>
                      ))}
                    </select>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs"
                    onClick={() => {
                      setSeverity("");
                      setIssueType("");
                    }}
                    disabled={!severity && !issueType}
                  >
                    Reset
                  </button>
                </div>
              </div>

              {data.issues.length === 0 ? (
                <div className="p-5">
                  <EmptyState
                    title="No issues match these filters"
                    message="Clear the filters to see the full issue register."
                  />
                </div>
              ) : (
                <div className="max-h-[640px] overflow-auto">
                  <table className="w-full min-w-[900px] text-sm">
                    <caption className="sr-only">
                      Data quality findings requiring review
                    </caption>
                    <thead>
                      <tr className="table-head">
                        <th scope="col" className="px-4 py-2.5 text-left">
                          Provider
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-left">
                          Specialty
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-left">
                          Month
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-left">
                          Issue type
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-left">
                          Severity
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-right">
                          Observed
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-right">
                          Reference
                        </th>
                        <th scope="col" className="px-4 py-2.5 text-left">
                          Detail
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {data.issues.map((issue, index) => (
                        <tr key={index} className="hover:bg-surface-subtle">
                          <td className="max-w-[180px] truncate px-4 py-2.5 text-ink-muted">
                            {issue.provider_name ?? "—"}
                          </td>
                          <td className="max-w-[150px] truncate px-4 py-2.5 text-ink-muted">
                            {issue.specialty_name ?? "—"}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 text-ink-muted">
                            {issue.month ? fmtMonth(issue.month) : "—"}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5 font-medium text-ink">
                            {issue.issue_type}
                          </td>
                          <td className="whitespace-nowrap px-4 py-2.5">
                            <span
                              className={`inline-block rounded-full border px-2 py-0.5 text-2xs font-semibold ${
                                SEVERITY_STYLES[issue.severity] ??
                                SEVERITY_STYLES.Low
                              }`}
                            >
                              {issue.severity}
                            </span>
                          </td>
                          <td className="tnum whitespace-nowrap px-4 py-2.5 text-right text-ink-muted">
                            {fmtCount(issue.observed_value)}
                          </td>
                          <td className="tnum whitespace-nowrap px-4 py-2.5 text-right text-ink-subtle">
                            {fmtCount(issue.expected_value)}
                          </td>
                          <td className="min-w-[320px] px-4 py-2.5 text-xs leading-relaxed text-ink-muted">
                            {issue.description}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="tnum mt-0.5 text-sm font-semibold text-ink">{value}</dd>
    </div>
  );
}
