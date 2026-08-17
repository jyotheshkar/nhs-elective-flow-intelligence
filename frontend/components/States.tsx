import Link from "next/link";

/** Loading, empty and error states used across every screen. */

export function LoadingSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3" role="status" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-4 w-full" />
      ))}
    </div>
  );
}

export function CardSkeleton({ height = "h-64" }: { height?: string }) {
  return (
    <div className="card p-5" role="status" aria-live="polite">
      <span className="sr-only">Loading</span>
      <div className="skeleton mb-4 h-4 w-1/3" />
      <div className={`skeleton w-full ${height}`} />
    </div>
  );
}

export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-surface-border bg-surface-subtle px-6 py-12 text-center">
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-1.5 max-w-md text-sm text-ink-muted">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  message,
  remedy = [],
  onRetry,
}: {
  title?: string;
  message: string;
  remedy?: string[];
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-band-criticalBorder bg-band-criticalBg p-5"
    >
      <p className="text-sm font-semibold text-band-critical">{title}</p>
      <p className="mt-1.5 text-sm text-ink-muted">{message}</p>
      {remedy.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {remedy.map((item) => (
            <li key={item} className="text-xs text-ink-muted">
              <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-[11px]">
                {item}
              </code>
            </li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn mt-4">
          Try again
        </button>
      )}
    </div>
  );
}

/**
 * Shown when the backend is reachable but no warehouse has been built.
 * This is a setup state with a specific remedy, so it is deliberately
 * distinguished from a generic failure.
 */
export function WarehouseMissingState({ message }: { message?: string }) {
  return (
    <div className="card p-8 text-center">
      <p className="text-base font-semibold text-ink">
        Official data is currently unavailable
      </p>
      <p className="mx-auto mt-2 max-w-lg text-sm text-ink-muted">
        {message ??
          "The analytics warehouse has not been built yet. Ingest the published NHS England statistics, or load the demonstration dataset."}
      </p>
      <div className="mx-auto mt-5 max-w-md space-y-2 text-left">
        <div className="rounded-md border border-surface-border bg-surface-muted p-3">
          <p className="label">Build from official NHS England data</p>
          <code className="mt-1 block font-mono text-xs text-ink">make data</code>
        </div>
        <div className="rounded-md border border-surface-border bg-surface-muted p-3">
          <p className="label">Or load the demonstration dataset</p>
          <code className="mt-1 block font-mono text-xs text-ink">make demo</code>
        </div>
      </div>
      <Link href="/methodology" className="btn mt-5">
        Read the methodology
      </Link>
    </div>
  );
}
