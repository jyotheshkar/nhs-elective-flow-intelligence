"use client";

import { useCallback, useEffect, useState } from "react";

import type { ApiError } from "@/lib/api";

interface Snapshot<T> {
  fetcher: Fetcher<T>;
  nonce: number;
  data: T | null;
  error: ApiError | null;
}

export type Fetcher<T> = (signal: AbortSignal) => Promise<T>;

export interface AsyncResource<T> {
  data: T | null;
  error: ApiError | null;
  /** True while the current request is in flight, including refetches. */
  loading: boolean;
  reload: () => void;
}

/**
 * Fetch an API resource with abort-on-unmount and a retry handle.
 *
 * `loading` is *derived* by comparing the latest snapshot against the current
 * fetcher identity, rather than stored in state and flipped at the top of the
 * effect. That avoids the cascading render that a synchronous `setState`
 * inside an effect body causes, and keeps previously-loaded data on screen
 * while a refetch is in flight instead of flashing a skeleton on every filter
 * change.
 *
 * `fetcher` must be stable across renders — wrap it in `useCallback` with the
 * values it actually depends on. Its identity is the cache key.
 */
export function useApiData<T>(fetcher: Fetcher<T>): AsyncResource<T> {
  const [nonce, setNonce] = useState(0);
  const [snapshot, setSnapshot] = useState<Snapshot<T> | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    fetcher(controller.signal)
      .then((data) => {
        if (active) setSnapshot({ fetcher, nonce, data, error: null });
      })
      .catch((error: ApiError) => {
        if (active && error?.name !== "AbortError") {
          setSnapshot({ fetcher, nonce, data: null, error });
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [fetcher, nonce]);

  const stale =
    snapshot === null || snapshot.fetcher !== fetcher || snapshot.nonce !== nonce;

  return {
    // Keep the previous payload visible during a refetch.
    data: snapshot?.data ?? null,
    error: stale ? null : (snapshot?.error ?? null),
    loading: stale,
    reload: useCallback(() => setNonce((n) => n + 1), []),
  };
}
