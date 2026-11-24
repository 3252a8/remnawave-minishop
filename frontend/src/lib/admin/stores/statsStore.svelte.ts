import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiClient,
  type GetResponse,
  buildAdminStatsPath,
  buildAdminSyncPath,
} from "../../webapp/publicApi";
import { defineRawStateProperty } from "./rawStateProperty";
import { fetchAdminQuery, type AdminQueryClient } from "./adminQueryCache";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = ApiClient["api"];
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type StatsResponse = GetResponse<"/api/admin/stats">;
export type StatsState = {
  stats: StatsResponse | null;
  panel: Record<string, unknown> | null;
  statsLoading: boolean;
  panelLoading: boolean;
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
const PANEL_QUERY_KEY = ["admin", "panel-stats"] as const;

class AdminStatsError extends Error {
  payload: unknown;

  constructor(message: string, payload: unknown) {
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
  let panel = $state.raw<StatsState["panel"]>(null);
  let pending: Promise<[void, void]> | null = null;
  const state = $state<Omit<StatsState, "stats" | "panel">>({
    statsLoading: false,
    panelLoading: false,
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
  defineRawStateProperty(store, "panel", {
    get: () => panel,
    set: (value) => {
      panel = value;
    },
  });

  async function requestStats(): Promise<StatsResponse> {
    const data = await api(`${buildAdminStatsPath()}?include_panel=false`);
    if (!isOkResponse(data)) {
      throw new AdminStatsError(adminErrorMessage(data, at, "load_failed"), data);
    }
    return data;
  }

  async function loadLocalStats(refresh: boolean): Promise<void> {
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

  async function loadPanelStats(refresh: boolean): Promise<void> {
    state.panelLoading = true;
    try {
      panel = await fetchAdminQuery({
        queryClient,
        queryKey: PANEL_QUERY_KEY,
        queryFn: async () => unwrap(await api("/admin/stats/panel")).panel,
        refresh,
      });
    } catch {
      panel = { error: "unavailable" };
    } finally {
      state.panelLoading = false;
    }
  }

  async function loadStats({ refresh = false }: { refresh?: boolean } = {}): Promise<void> {
    if (pending) {
      await pending;
      if (refresh) await loadStats({ refresh });
      return;
    }
    pending = Promise.all([loadLocalStats(refresh), loadPanelStats(refresh)]);
    try {
      await pending;
    } finally {
      pending = null;
    }
  }

  async function triggerSync(): Promise<void> {
    if (state.syncBusy) return;

    state.syncBusy = true;
    try {
      const res = await api(buildAdminSyncPath(), { method: "POST" });
      if (isOkResponse(res)) {
        onToast(at("sync_started", {}, "Synchronization started"));
        await loadStats({ refresh: true });
      } else {
        onToast(adminErrorMessage(res, at, at("sync_error", {}, "Synchronization error")));
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
