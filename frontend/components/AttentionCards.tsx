import Link from "next/link";

import PriorityBadge from "@/components/PriorityBadge";
import { fmtCount, fmtScore } from "@/lib/format";
import type { AttentionCard } from "@/types/api";

/**
 * "What needs attention" — the product's core answer, rendered as ranked cards
 * with the specific evidence that put each service on the list.
 */
export default function AttentionCards({ cards }: { cards: AttentionCard[] }) {
  if (cards.length === 0) {
    return (
      <p className="px-5 py-8 text-center text-sm text-ink-subtle">
        No services meet the ranking threshold in the current selection.
      </p>
    );
  }

  return (
    <ol className="divide-y divide-surface-border">
      {cards.map((card) => (
        <li key={`${card.provider_code}-${card.specialty_code}`}>
          <Link
            href={`/service/${encodeURIComponent(
              card.provider_code,
            )}/${encodeURIComponent(card.specialty_code)}`}
            className="block px-5 py-4 transition-colors hover:bg-surface-subtle"
          >
            <div className="flex items-start gap-3">
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-surface-muted text-xs font-bold text-ink-muted"
              >
                {card.rank}
              </span>

              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-ink">
                      {card.specialty_name}
                    </p>
                    <p className="truncate text-xs text-ink-subtle">
                      {card.provider_name}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="tnum text-lg font-semibold text-ink">
                      {fmtScore(card.priority_score)}
                    </span>
                    <PriorityBadge band={card.priority_band} />
                  </div>
                </div>

                <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
                  {card.reasons.map((reason) => (
                    <li
                      key={reason}
                      className="text-2xs text-ink-muted before:mr-1 before:text-ink-subtle before:content-['•']"
                    >
                      {reason}
                    </li>
                  ))}
                </ul>

                <p className="mt-1.5 text-2xs text-ink-subtle">
                  Waiting list {fmtCount(card.waiting_list)} pathways
                </p>
              </div>
            </div>
          </Link>
        </li>
      ))}
    </ol>
  );
}
