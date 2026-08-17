"use client";

import { useEffect, useId, useRef, useState } from "react";

interface Props {
  title: string;
  definition: string;
  source?: string;
  calculation?: string;
}

/**
 * Keyboard-accessible metric explainer.
 *
 * Implemented as a toggle button with `aria-expanded` rather than a hover-only
 * tooltip: hover tooltips are unreachable by keyboard and unusable on touch,
 * and these definitions are the difference between a number being trustworthy
 * and being decorative.
 */
export default function InfoTooltip({
  title,
  definition,
  source,
  calculation,
}: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;

    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span className="relative inline-block" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`How "${title}" is defined and calculated`}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-surface-border bg-surface-muted text-[10px] font-bold leading-none text-ink-subtle transition-colors hover:bg-slate-200 hover:text-ink"
      >
        i
      </button>

      {open && (
        <span
          id={panelId}
          role="dialog"
          aria-label={`${title} definition`}
          className="absolute left-0 top-6 z-50 block w-72 rounded-lg border border-surface-border bg-surface p-3 text-left shadow-raised sm:w-80"
        >
          <span className="block text-xs font-semibold text-ink">{title}</span>
          <span className="mt-1.5 block text-xs leading-relaxed text-ink-muted">
            {definition}
          </span>
          {calculation && (
            <span className="mt-2 block">
              <span className="label block">Calculation</span>
              <span className="mt-0.5 block whitespace-pre-line font-mono text-[11px] leading-relaxed text-ink-muted">
                {calculation}
              </span>
            </span>
          )}
          {source && (
            <span className="mt-2 block">
              <span className="label block">Source</span>
              <span className="mt-0.5 block text-[11px] leading-relaxed text-ink-subtle">
                {source}
              </span>
            </span>
          )}
        </span>
      )}
    </span>
  );
}
