"use client";

import { useCallback } from "react";

import { api } from "@/lib/api";
import { useApiData } from "@/lib/useApiData";
import type { Provider, Region, Specialty } from "@/types/api";

export interface ReferenceData {
  providers: Provider[];
  specialties: Specialty[];
  regions: Region[];
}

const EMPTY: ReferenceData = { providers: [], specialties: [], regions: [] };

/** Providers, specialties and regions — loaded once, used by every filter. */
export function useReferenceData() {
  const fetcher = useCallback(async (signal: AbortSignal) => {
    const [providers, specialties, regions] = await Promise.all([
      api.providers(signal),
      api.specialties(signal),
      api.regions(signal),
    ]);
    return { providers, specialties, regions } satisfies ReferenceData;
  }, []);

  const resource = useApiData<ReferenceData>(fetcher);
  return { ...resource, data: resource.data ?? EMPTY };
}
