import InfoTooltip from "@/components/InfoTooltip";
import { TONE_CLASS, movementGlyph, movementTone } from "@/lib/format";
import type { KpiCard } from "@/types/api";

export default function KpiRow({ kpis }: { kpis: KpiCard[] }) {
  if (kpis.length === 0) return null;

  return (
    <section aria-label="Executive summary metrics">
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {kpis.map((kpi) => {
          const tone = movementTone(
            kpi.secondary_value,
            kpi.higher_is_better ?? false,
          );
          return (
            <li key={kpi.key} className="card p-4">
              <div className="flex items-start justify-between gap-2">
                <h3 className="label">{kpi.label}</h3>
                <InfoTooltip
                  title={kpi.label}
                  definition={kpi.definition}
                  source={kpi.source}
                  calculation={kpi.calculation}
                />
              </div>

              <p
                className="tnum mt-2 truncate text-2xl font-semibold tracking-tight text-ink"
                title={kpi.display_value}
              >
                {kpi.display_value}
              </p>

              {kpi.secondary_display && (
                <p className="mt-1.5 flex items-baseline gap-1.5 text-xs">
                  <span
                    className={`tnum font-semibold ${
                      kpi.direction === "none" ? "text-ink-muted" : TONE_CLASS[tone]
                    }`}
                  >
                    {kpi.direction !== "none" && (
                      <span aria-hidden="true" className="mr-0.5">
                        {movementGlyph(kpi.secondary_value)}
                      </span>
                    )}
                    {kpi.secondary_display}
                  </span>
                  <span className="truncate text-ink-subtle">
                    {kpi.secondary_label}
                  </span>
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
