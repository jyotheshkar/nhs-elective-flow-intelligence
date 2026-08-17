import { fmtDecimal } from "@/lib/format";
import type { ScoreComponent } from "@/types/api";

/**
 * "Why this score?" — the priority index decomposed into its weighted parts.
 *
 * Each bar shows the contribution earned against the maximum available for
 * that component, so the arithmetic is visible: the bars sum to the total.
 */
export default function ScoreBreakdown({
  components,
  total,
  drivers = [],
}: {
  components: ScoreComponent[];
  total?: number | null;
  drivers?: string[];
}) {
  const summed = components.reduce((acc, c) => acc + (c.contribution ?? 0), 0);

  return (
    <div className="space-y-4">
      <ul className="space-y-3">
        {components.map((component) => {
          const contribution = component.contribution ?? 0;
          const share = (contribution / component.max_contribution) * 100;
          return (
            <li key={component.key}>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-xs font-medium text-ink">
                  {component.label}
                </span>
                <span className="tnum shrink-0 text-xs text-ink-muted">
                  <span className="font-semibold text-ink">
                    {fmtDecimal(contribution, 1)}
                  </span>
                  {" / "}
                  {component.max_contribution}
                </span>
              </div>

              <div
                className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-muted"
                role="img"
                aria-label={`${component.label}: ${fmtDecimal(
                  contribution,
                  1,
                )} of ${component.max_contribution} points`}
              >
                <div
                  className="h-full rounded-full bg-brand-600"
                  style={{ width: `${Math.min(Math.max(share, 0), 100)}%` }}
                />
              </div>

              <p className="mt-1 text-2xs leading-relaxed text-ink-subtle">
                Component score {fmtDecimal(component.score, 0)}/100 ·{" "}
                {component.description}
              </p>
            </li>
          );
        })}
      </ul>

      <div className="flex items-baseline justify-between border-t border-surface-border pt-3">
        <span className="text-sm font-semibold text-ink">Total</span>
        <span className="tnum text-sm font-bold text-ink">
          {fmtDecimal(total ?? summed, 1)} / 100
        </span>
      </div>

      {drivers.length > 0 && (
        <div className="rounded-md border border-surface-border bg-surface-subtle p-3">
          <p className="label">Why is this being flagged?</p>
          <ul className="mt-2 space-y-1.5">
            {drivers.map((driver) => (
              <li
                key={driver}
                className="flex gap-2 text-xs leading-relaxed text-ink-muted"
              >
                <span aria-hidden="true" className="text-brand-600">
                  +
                </span>
                <span>{driver}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
