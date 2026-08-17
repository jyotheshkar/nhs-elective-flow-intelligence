"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { DataProvenance } from "@/types/api";

import SiteFooter from "./SiteFooter";
import SiteHeader from "./SiteHeader";

/**
 * Loads provenance once for the whole application.
 *
 * The header and footer must always be able to state where the numbers came
 * from, including when the warehouse is missing - so a failure here is
 * swallowed and simply leaves the provenance strip empty rather than blocking
 * the page.
 */
export default function AppShell({ children }: { children: React.ReactNode }) {
  const [provenance, setProvenance] = useState<DataProvenance | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .metadata(controller.signal)
      .then((meta) => setProvenance(meta.provenance))
      .catch(() => setProvenance(null));
    return () => controller.abort();
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <SiteHeader provenance={provenance} />
      <main id="main" className="flex-1">
        {children}
      </main>
      <SiteFooter provenance={provenance} />
    </div>
  );
}
