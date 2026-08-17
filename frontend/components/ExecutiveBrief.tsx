import PriorityBadge from "@/components/PriorityBadge";
import type { Briefing } from "@/types/api";

/**
 * Executive brief.
 *
 * Every sentence is assembled server-side from computed values by a
 * deterministic rules engine — no language model is involved in the default
 * path. The generation method is stated on the panel so a reader knows the
 * prose cannot have invented anything.
 */
export default function ExecutiveBrief({ briefing }: { briefing: Briefing }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm font-medium leading-relaxed text-ink">
          {briefing.headline}
        </p>
        <PriorityBadge
          band={briefing.priority_band}
          score={briefing.priority_score}
          size="md"
          showScore
        />
      </div>

      <dl className="space-y-3">
        {briefing.sections.map((section) => (
          <div key={section.title}>
            <dt className="label">{section.title}</dt>
            <dd className="mt-0.5 text-sm leading-relaxed text-ink-muted">
              {section.body}
            </dd>
          </div>
        ))}
      </dl>

      {briefing.recommended_actions.length > 0 && (
        <div className="rounded-md border border-surface-border bg-surface-subtle p-3">
          <p className="label">Suggested next steps</p>
          <ol className="mt-2 space-y-1.5">
            {briefing.recommended_actions.map((action, index) => (
              <li
                key={action}
                className="flex gap-2 text-xs leading-relaxed text-ink-muted"
              >
                <span
                  aria-hidden="true"
                  className="shrink-0 font-semibold text-ink-subtle"
                >
                  {index + 1}.
                </span>
                <span>{action}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      <div className="border-t border-surface-border pt-3">
        <p className="text-2xs font-medium text-ink-subtle">
          Generated from computed values by a deterministic rules engine
          {briefing.generated_by === "deterministic_rules"
            ? " (no language model involved)"
            : ""}
          .
        </p>
        <ul className="mt-1.5 space-y-1">
          {briefing.caveats.map((caveat) => (
            <li key={caveat} className="text-2xs leading-relaxed text-ink-subtle">
              · {caveat}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
