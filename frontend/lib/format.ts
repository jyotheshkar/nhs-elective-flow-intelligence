/** Shared value formatting. One place, so every screen renders numbers alike. */

const NUMBER = new Intl.NumberFormat("en-GB");

export function isNum(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

/** Whole-number count, e.g. "12,438". */
export function fmtCount(value?: number | null, fallback = "—"): string {
  return isNum(value) ? NUMBER.format(Math.round(value)) : fallback;
}

/** Compact count for axis ticks, e.g. "12.4k". */
export function fmtCompact(value?: number | null, fallback = "—"): string {
  if (!isNum(value)) return fallback;
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}m`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(abs >= 10_000 ? 0 : 1)}k`;
  return NUMBER.format(Math.round(value));
}

export function fmtPct(
  value?: number | null,
  places = 1,
  fallback = "—",
): string {
  return isNum(value) ? `${value.toFixed(places)}%` : fallback;
}

export function fmtSignedPct(
  value?: number | null,
  places = 1,
  fallback = "—",
): string {
  return isNum(value) ? `${value >= 0 ? "+" : ""}${value.toFixed(places)}%` : fallback;
}

export function fmtSignedCount(value?: number | null, fallback = "—"): string {
  if (!isNum(value)) return fallback;
  return `${value >= 0 ? "+" : "−"}${NUMBER.format(Math.abs(Math.round(value)))}`;
}

export function fmtDecimal(
  value?: number | null,
  places = 1,
  fallback = "—",
): string {
  return isNum(value) ? value.toFixed(places) : fallback;
}

export function fmtScore(value?: number | null, fallback = "—"): string {
  return isNum(value) ? `${Math.round(value)}` : fallback;
}

/** "2026-03" -> "Mar 2026". */
export function fmtMonth(monthKey?: string | null): string {
  if (!monthKey) return "—";
  const [year, month] = monthKey.split("-");
  const index = Number(month) - 1;
  const names = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  ];
  return index >= 0 && index < 12 ? `${names[index]} ${year}` : monthKey;
}

/** ISO timestamp -> "17 Aug 2026". */
export function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/**
 * Direction of travel with the right polarity.
 * Returns the semantic meaning, not the arithmetic sign, so the UI can colour
 * a falling waiting list green and a falling 18-week percentage red.
 */
export function movementTone(
  value?: number | null,
  higherIsBetter = false,
  threshold = 0.05,
): "good" | "bad" | "neutral" {
  if (!isNum(value) || Math.abs(value) < threshold) return "neutral";
  const rising = value > 0;
  return rising === higherIsBetter ? "good" : "bad";
}

export const TONE_CLASS: Record<"good" | "bad" | "neutral", string> = {
  good: "text-band-low",
  bad: "text-band-critical",
  neutral: "text-ink-subtle",
};

/** ▲ / ▼ / — glyphs so direction is never conveyed by colour alone. */
export function movementGlyph(value?: number | null, threshold = 0.05): string {
  if (!isNum(value) || Math.abs(value) < threshold) return "—";
  return value > 0 ? "▲" : "▼";
}
