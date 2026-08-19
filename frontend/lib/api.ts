/**
 * Typed API client.
 *
 * Every call goes through `request`, which normalises the two failure modes the
 * UI needs to distinguish: the backend being unreachable, and the backend
 * reporting that no warehouse has been built (HTTP 503). The second is a
 * recoverable setup state with a specific remedy, so it gets its own error type
 * rather than being rendered as a generic failure.
 */

import type {
  ComparisonResponse,
  DataQualityResponse,
  ForecastResponse,
  Metadata,
  MethodologyResponse,
  OverviewResponse,
  Provider,
  ProviderDetailResponse,
  RankingsResponse,
  Region,
  ReportingPeriod,
  ScenarioResponse,
  ServiceDetailResponse,
  Specialty,
  TimeseriesResponse,
} from "@/types/api";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

const API_PREFIX = "/api/v1";

export class ApiError extends Error {
  status: number;
  remedy: string[];
  isWarehouseMissing: boolean;

  constructor(
    message: string,
    status: number,
    remedy: string[] = [],
    isWarehouseMissing = false,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.remedy = remedy;
    this.isWarehouseMissing = isWarehouseMissing;
  }
}

export class ApiUnreachableError extends ApiError {
  constructor(message: string) {
    super(message, 0, [
      "If running locally: uvicorn app.main:app --reload (from ./backend)",
      "Free-tier hosting sleeps after inactivity; the first request can take up to a minute.",
    ]);
    this.name = "ApiUnreachableError";
  }
}

/**
 * The backend is hosted on a free tier that sleeps after inactivity, so the
 * first request after a quiet period can time out or refuse connections while
 * the service cold-starts. GET requests therefore retry with backoff before
 * surfacing an error. Mutating requests are never retried automatically.
 */
const COLD_START_RETRY_DELAYS_MS = [2000, 5000, 10000];

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      },
      { once: true },
    );
  });
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
  /** Server components should not cache analytics responses across builds. */
  cache?: RequestCache;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = `${API_BASE}${API_PREFIX}${path}`;
  const method = options.method ?? "GET";
  let response: Response;

  const attemptFetch = () =>
    fetch(url, {
      method,
      headers: options.body ? { "Content-Type": "application/json" } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      cache: options.cache ?? "no-store",
    });

  try {
    response = await attemptFetch();
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    // Cold-start tolerance: retry idempotent reads with backoff.
    if (method === "GET") {
      let recovered: Response | null = null;
      for (const delay of COLD_START_RETRY_DELAYS_MS) {
        try {
          await sleep(delay, options.signal);
          recovered = await attemptFetch();
          break;
        } catch (retryError) {
          if ((retryError as Error).name === "AbortError") throw retryError;
        }
      }
      if (recovered) {
        response = recovered;
      } else {
        throw new ApiUnreachableError(
          `The analytics service at ${API_BASE} is not responding. This free ` +
            "portfolio deployment sleeps after inactivity and can take up to " +
            "a minute to wake - please retry shortly.",
        );
      }
    } else {
      throw new ApiUnreachableError(
        `Cannot reach the analytics API at ${API_BASE}. The free-tier backend ` +
          "may be waking from sleep - please retry in a few seconds.",
      );
    }
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    let remedy: string[] = [];
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") detail = payload.detail;
      if (Array.isArray(payload?.remedy)) remedy = payload.remedy;
    } catch {
      /* response had no JSON body; keep the default message */
    }
    throw new ApiError(detail, response.status, remedy, response.status === 503);
  }

  return (await response.json()) as T;
}

/** Build a query string, dropping empty values. */
function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.append(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export interface DashboardFilters {
  provider_code?: string;
  specialty_code?: string;
  region?: string;
  priority_band?: string;
  search?: string;
}

export const api = {
  metadata: (signal?: AbortSignal) =>
    request<Metadata>("/metadata", { signal }),

  providers: (signal?: AbortSignal) =>
    request<Provider[]>("/providers", { signal }),

  specialties: (signal?: AbortSignal) =>
    request<Specialty[]>("/specialties", { signal }),

  regions: (signal?: AbortSignal) => request<Region[]>("/regions", { signal }),

  reportingPeriods: (signal?: AbortSignal) =>
    request<ReportingPeriod[]>("/reporting-periods", { signal }),

  overview: (filters: DashboardFilters = {}, signal?: AbortSignal) =>
    request<OverviewResponse>(`/overview${qs({ ...filters })}`, { signal }),

  rankings: (
    params: DashboardFilters & {
      sort_by?: string;
      descending?: boolean;
      limit?: number;
      offset?: number;
      rankable_only?: boolean;
    } = {},
    signal?: AbortSignal,
  ) => request<RankingsResponse>(`/rankings${qs({ ...params })}`, { signal }),

  rankingsExportUrl: (
    params: DashboardFilters & { sort_by?: string; descending?: boolean } = {},
  ) => `${API_BASE}${API_PREFIX}/rankings/export${qs({ ...params })}`,

  timeseries: (
    params: {
      provider_code?: string;
      specialty_code?: string;
      include_forecast?: boolean;
    },
    signal?: AbortSignal,
  ) => request<TimeseriesResponse>(`/timeseries${qs({ ...params })}`, { signal }),

  forecast: (
    provider_code: string,
    specialty_code: string,
    signal?: AbortSignal,
  ) =>
    request<ForecastResponse>(
      `/forecast${qs({ provider_code, specialty_code })}`,
      { signal },
    ),

  serviceDetail: (
    providerCode: string,
    specialtyCode: string,
    scenarioUplift = 10,
    signal?: AbortSignal,
  ) =>
    request<ServiceDetailResponse>(
      `/service/${encodeURIComponent(providerCode)}/${encodeURIComponent(
        specialtyCode,
      )}${qs({ scenario_uplift_pct: scenarioUplift })}`,
      { signal },
    ),

  providerDetail: (providerCode: string, signal?: AbortSignal) =>
    request<ProviderDetailResponse>(
      `/provider/${encodeURIComponent(providerCode)}`,
      { signal },
    ),

  scenario: (
    body: {
      provider_code: string;
      specialty_code: string;
      uplift_pct: number;
      compare_uplifts?: number[];
    },
    signal?: AbortSignal,
  ) => request<ScenarioResponse>("/scenario", { method: "POST", body, signal }),

  compare: (
    specialtyCode: string,
    providerCodes: string[],
    signal?: AbortSignal,
  ) => {
    const search = new URLSearchParams({ specialty_code: specialtyCode });
    providerCodes.forEach((code) => search.append("provider_codes", code));
    return request<ComparisonResponse>(`/compare?${search.toString()}`, { signal });
  },

  dataQuality: (
    params: {
      severity?: string;
      issue_type?: string;
      provider_code?: string;
      limit?: number;
    } = {},
    signal?: AbortSignal,
  ) => request<DataQualityResponse>(`/data-quality${qs({ ...params })}`, { signal }),

  methodology: (signal?: AbortSignal) =>
    request<MethodologyResponse>("/methodology", { signal }),
};
