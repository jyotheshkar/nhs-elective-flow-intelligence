import type { PriorityBand } from "@/types/api";

/**
 * Priority band indicator.
 *
 * Accessibility: the band is conveyed by three redundant channels - a text
 * label, a shape glyph and a colour. Removing colour (greyscale print,
 * colour-blind users) leaves the meaning fully intact.
 */
const BAND_STYLES: Record<
  PriorityBand,
  { label: string; glyph: string; classes: string }
> = {
  CRITICAL: {
    label: "Critical",
    glyph: "■",
    classes: "bg-band-criticalBg text-band-critical border-band-criticalBorder",
  },
  HIGH: {
    label: "High",
    glyph: "▲",
    classes: "bg-band-highBg text-band-high border-band-highBorder",
  },
  MODERATE: {
    label: "Moderate",
    glyph: "◆",
    classes: "bg-band-moderateBg text-band-moderate border-band-moderateBorder",
  },
  LOW: {
    label: "Low",
    glyph: "●",
    classes: "bg-band-lowBg text-band-low border-band-lowBorder",
  },
  UNSCORED: {
    label: "Unscored",
    glyph: "○",
    classes: "bg-surface-muted text-ink-subtle border-surface-border",
  },
};

export function bandStyle(band?: PriorityBand | string | null) {
  const key = (band ?? "UNSCORED") as PriorityBand;
  return BAND_STYLES[key] ?? BAND_STYLES.UNSCORED;
}

/** Hex colours for chart marks, matching the badge palette. */
export const BAND_CHART_COLOURS: Record<string, string> = {
  CRITICAL: "#b91c1c",
  HIGH: "#c2410c",
  MODERATE: "#a16207",
  LOW: "#007f3b",
  UNSCORED: "#8494ad",
};

interface Props {
  band?: PriorityBand | string | null;
  score?: number | null;
  size?: "sm" | "md";
  showScore?: boolean;
}

export default function PriorityBadge({
  band,
  score,
  size = "sm",
  showScore = false,
}: Props) {
  const style = bandStyle(band);
  const padding = size === "md" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-2xs";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold uppercase tracking-wide ${padding} ${style.classes}`}
    >
      <span aria-hidden="true">{style.glyph}</span>
      <span>{style.label}</span>
      {showScore && typeof score === "number" && (
        <span className="tnum font-bold">{Math.round(score)}</span>
      )}
    </span>
  );
}
