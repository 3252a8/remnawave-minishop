import { adminErrorMessage } from "../errors.js";
import { unwrap, type ApiResponse, type GetResponse } from "../../webapp/publicApi";

const HEALTH_QUERY_KEY = ["admin", "health"] as const;
const HEALTH_STALE_MS = 60 * 1000;

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type HealthResponse = GetResponse<"/api/admin/health">;
type HealthQueryKey = typeof HEALTH_QUERY_KEY;
type HealthQueryClient = {
  invalidateQueries: (options: { queryKey: HealthQueryKey }) => Promise<unknown>;
  fetchQuery: (options: {
    queryKey: HealthQueryKey;
    queryFn: () => Promise<HealthResponse>;
    retry: false;
    staleTime: number;
  }) => Promise<HealthResponse>;
};
export type HealthAlert = {
  id: string | number;
  severity: string;
  message_key: string;
  params: Record<string, unknown>;
  sections: string[];
};
type HealthState = {
  alerts: HealthAlert[];
  checkedAt: string | null;
  healthLoading: boolean;
  healthError: string;
};
type HealthStoreOptions = {
  api: AdminApi;
  at?: TranslateFn;
  queryClient?: HealthQueryClient | null;
};
export type HealthStore = HealthState & {
  loadHealth: (options?: { refresh?: boolean }) => Promise<void>;
};

class AdminHealthError extends Error {
  payload: AdminErrorResponse | null;

  constructor(message: string, payload: AdminErrorResponse | null) {
    super(message);
    this.name = "AdminHealthError";
    this.payload = payload;
  }
}

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function normalizeAlert(value: unknown): HealthAlert {
  const alert = asRecord(value);
  const messageKey = typeof alert.message_key === "string" ? alert.message_key : "";
  const rawId = alert.id;
  return {
    id: typeof rawId === "string" || typeof rawId === "number" ? rawId : messageKey,
    severity: typeof alert.severity === "string" ? alert.severity : "warning",
    message_key: messageKey,
    params: asRecord(alert.params),
    sections: asStringArray(alert.sections),
  };
}

function normalizeAlerts(alerts: unknown): HealthAlert[] {
  return Array.isArray(alerts) ? alerts.map(normalizeAlert) : [];
}

export function createHealthStore({
  api,
  at = (key, _params, fallback) => fallback || key,
  queryClient = null,
}: HealthStoreOptions): HealthStore {
  const state = $state<HealthState>({
    alerts: [],
    checkedAt: null,
    healthLoading: false,
    healthError: "",
  });

  function healthErrorMessage(error: unknown): string {
    if (error instanceof AdminHealthError && error.payload) {
      return adminErrorMessage(error.payload, at, "load_failed");
    }
    return error instanceof Error ? error.message : String(error);
  }

  async function requestHealth(refresh: boolean): Promise<HealthResponse> {
    const data = (await api(`/admin/health${refresh ? "?refresh=1" : ""}`)) as
      | HealthResponse
      | AdminErrorResponse;
    if (!isOkResponse(data)) {
      throw new AdminHealthError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return unwrap(data);
  }

  async function queryHealth(refresh: boolean): Promise<HealthResponse> {
    if (!queryClient) return requestHealth(refresh);
    if (refresh) await queryClient.invalidateQueries({ queryKey: HEALTH_QUERY_KEY });
    return queryClient.fetchQuery({
      queryKey: HEALTH_QUERY_KEY,
      queryFn: () => requestHealth(refresh),
      retry: false,
      staleTime: HEALTH_STALE_MS,
    });
  }

  async function loadHealth({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    state.healthLoading = true;
    state.healthError = "";
    try {
      const data = await queryHealth(refresh);
      state.alerts = normalizeAlerts(data.alerts);
      state.checkedAt = data.checked_at || null;
    } catch (e: unknown) {
      state.healthError = healthErrorMessage(e);
    } finally {
      state.healthLoading = false;
    }
  }

  return Object.assign(state, {
    loadHealth,
  });
}
