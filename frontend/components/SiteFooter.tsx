import Link from "next/link";

import { fmtDate } from "@/lib/format";
import type { DataProvenance } from "@/types/api";

export default function SiteFooter({
  provenance,
}: {
  provenance?: DataProvenance | null;
}) {
  return (
    <footer className="mt-12 border-t border-surface-border bg-surface">
      <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6">
        <div className="grid gap-8 md:grid-cols-3">
          <div>
            <h2 className="label">Data provenance</h2>
            <dl className="mt-2 space-y-1 text-xs text-ink-muted">
              <div className="flex gap-2">
                <dt className="text-ink-subtle">Source:</dt>
                <dd>{provenance?.source_name ?? "—"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-ink-subtle">Latest reporting period:</dt>
                <dd>{provenance?.latest_reporting_month_label ?? "—"}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-ink-subtle">Periods loaded:</dt>
                <dd>{provenance?.reporting_months ?? 0} months</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-ink-subtle">Retrieved:</dt>
                <dd>{fmtDate(provenance?.retrieved_at)}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-ink-subtle">Data type:</dt>
                <dd className="font-mono">
                  {provenance?.data_source_type ?? "—"}
                </dd>
              </div>
              {provenance?.licence && (
                <div className="flex gap-2">
                  <dt className="text-ink-subtle">Licence:</dt>
                  <dd>{provenance.licence}</dd>
                </div>
              )}
            </dl>
          </div>

          <div>
            <h2 className="label">Responsible use</h2>
            <ul className="mt-2 space-y-1.5 text-xs text-ink-muted">
              <li>
                Aggregate public operational statistics only. No patient-level
                data is used, held or inferred.
              </li>
              <li>
                Not a clinical decision support, triage or diagnosis system.
              </li>
              <li>
                Forecasts and scenarios are modelled estimates, not observed
                effects, and imply no causal relationship.
              </li>
              <li>
                Priority scores are derived measures produced by this
                application, not NHS England statistics.
              </li>
            </ul>
          </div>

          <div>
            <h2 className="label">Explore</h2>
            <ul className="mt-2 space-y-1.5 text-xs">
              <li>
                <Link href="/methodology" className="text-brand-700 hover:underline">
                  How it works — full methodology
                </Link>
              </li>
              <li>
                <Link href="/quality" className="text-brand-700 hover:underline">
                  Data quality monitor
                </Link>
              </li>
              {provenance?.source_landing_page && (
                <li>
                  <a
                    href={provenance.source_landing_page}
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand-700 hover:underline"
                  >
                    NHS England RTT publication ↗
                  </a>
                </li>
              )}
            </ul>
          </div>
        </div>

        <p className="mt-8 border-t border-surface-border pt-5 text-xs text-ink-subtle">
          Independent portfolio prototype using publicly available NHS England
          data. Not affiliated with or endorsed by NHS England.
          {provenance?.attribution ? ` ${provenance.attribution}` : ""}
        </p>
      </div>
    </footer>
  );
}
