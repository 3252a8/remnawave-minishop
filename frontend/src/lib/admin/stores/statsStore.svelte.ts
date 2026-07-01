import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiClient,
  type ApiResponse,
  type GetResponse,
  type PostResponse,
  buildAdminStatsPath,
  buildAdminSyncPath,
} from "../../webapp/publicApi";
import { defineRawStateProperty } from "./rawStateProperty";
import { fetchAdminQuery, invalidateAdminQuery, type AdminQueryClient } from "./adminQueryCache";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type StatsResponse = GetResponse<"/api/admin/stats">;
type SyncResponse = PostResponse<"/api/admin/sync">;
export type StatsState = {
  stats: StatsResponse | null;
  statsLoading: boolean;
  statsError: string;
  syncBusy: boolean;
};
type StatsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
  queryClient?: AdminQueryClient | null;
};
export type StatsStore = StatsState & {
  loadStats: (options?: { refresh?: boolean }) => Promise<void>;
  triggerSync: () => Promise<void>;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

const STATS_QUERY_KEY = ["admin", "stats"] as const;

class AdminStatsError extends Error {
  payload: AdminErrorResponse;

  constructor(message: string, payload: AdminErrorResponse) {
    super(message);
    this.payload = payload;
  }
}

export function createStatsStore({
  api,
  onToast,
  at,
  queryClient = null,
}: StatsStoreOptions): StatsStore {
  let stats = $state.raw<StatsResponse | null>(null);
  const state = $state<Omit<StatsState, "stats">>({
    statsLoading: false,
    statsError: "",
    syncBusy: false,
  });
  const store = Object.create(state) as StatsStore;
  defineRawStateProperty(store, "stats", {
    get: () => stats,
    set: (value) => {
      stats = value;
    },
  });

  async function requestStats(): Promise<StatsResponse> {
    const data = (await api(buildAdminStatsPath())) as StatsResponse | AdminErrorResponse;
    if (!isOkResponse(data)) {
      throw new AdminStatsError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return data;
  }

  async function loadStats({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    state.statsLoading = true;
    state.statsError = "";
    try {
      const data = await fetchAdminQuery({
        queryClient,
        queryKey: STATS_QUERY_KEY,
        queryFn: requestStats,
        refresh,
      });
      stats = unwrap(data);
    } catch (e: unknown) {
      if (e instanceof AdminStatsError) {
        state.statsError = adminErrorMessage(e.payload, at, "load_failed");
        return;
      }
      state.statsError = e instanceof Error ? e.message : String(e);
    } finally {
      state.statsLoading = false;
    }
  }

  async function triggerSync(): Promise<void> {
    if (state.syncBusy) return;

    state.syncBusy = true;
    try {
      const res = (await api(buildAdminSyncPath(), { method: "POST" })) as
        SyncResponse | AdminErrorResponse;
      if (isOkResponse(res)) {
        invalidateAdminQuery(queryClient, STATS_QUERY_KEY);
        onToast(at("sync_started", {}, "Синхронизация запущена"));
        await loadStats({ refresh: true });
      } else {
        onToast(adminErrorMessage(res, at, at("sync_error", {}, "Ошибка синхронизации")));
      }
    } finally {
      state.syncBusy = false;
    }
  }

  return Object.assign(store, {
    loadStats,
    triggerSync,
  });
}
