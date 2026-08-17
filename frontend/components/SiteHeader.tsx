"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import type { DataProvenance } from "@/types/api";

const NAV = [
  { href: "/", label: "Control Room" },
  { href: "/rankings", label: "Rankings" },
  { href: "/compare", label: "Compare" },
  { href: "/quality", label: "Data Quality" },
  { href: "/methodology", label: "How It Works" },
];

interface Props {
  provenance?: DataProvenance | null;
}

export default function SiteHeader({ provenance }: Props) {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-surface-border bg-surface/95 backdrop-blur">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded focus:bg-brand-700 focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to main content
      </a>

      <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5">
          <span
            aria-hidden="true"
            className="flex h-7 w-7 items-center justify-center rounded bg-brand-800 text-xs font-bold text-white"
          >
            EF
          </span>
          <span className="leading-tight">
            <span className="block text-sm font-semibold tracking-tight text-ink">
              NHS Elective Flow Intelligence
            </span>
            <span className="hidden text-2xs text-ink-subtle sm:block">
              Operational decision intelligence for elective waiting lists
            </span>
          </span>
        </Link>

        <nav aria-label="Primary" className="order-3 w-full lg:order-2 lg:w-auto">
          <ul className="flex flex-wrap items-center gap-1">
            {NAV.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`inline-flex h-8 items-center rounded-md px-3 text-sm font-medium transition-colors ${
                      active
                        ? "bg-brand-50 text-brand-800"
                        : "text-ink-muted hover:bg-surface-muted hover:text-ink"
                    }`}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="order-2 ml-auto flex items-center gap-3 lg:order-3">
          {provenance && (
            <div className="hidden text-right sm:block">
              <p className="text-2xs text-ink-subtle">
                Latest data:{" "}
                <span className="font-semibold text-ink-muted">
                  {provenance.latest_reporting_month_label ?? "—"}
                </span>
              </p>
              <p className="text-2xs text-ink-subtle">
                Source:{" "}
                <span className="font-semibold text-ink-muted">
                  {provenance.is_demo ? "Synthetic demo data" : "NHS England"}
                </span>
              </p>
            </div>
          )}
          <a
            href={`${
              process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"
            }/docs`}
            target="_blank"
            rel="noreferrer"
            className="btn btn-ghost hidden text-xs md:inline-flex"
          >
            API docs ↗
          </a>
        </div>
      </div>

      {provenance?.is_demo && (
        <div
          role="status"
          className="border-t border-band-moderateBorder bg-band-moderateBg px-4 py-2 text-center sm:px-6"
        >
          <p className="text-xs font-semibold text-band-moderate">
            ⚠ DEMO DATA — illustrative only. These figures are synthetic and are
            not NHS England statistics.
          </p>
        </div>
      )}
    </header>
  );
}
