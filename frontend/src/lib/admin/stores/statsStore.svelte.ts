import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiResponse,
  type GetResponse,
  type PostResponse,
} from "../../webapp/publicApi";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
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
};
export type StatsStore = StatsState & {
  loadStats: () => Promise<void>;
  triggerSync: () => Promise<void>;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

export function createStatsStore({ api, onToast, at }: StatsStoreOptions): StatsStore {
  const state = $state<StatsState>({
    stats: null,
    statsLoading: false,
    statsError: "",
    syncBusy: false,
  });

  async function loadStats(): Promise<void> {
    state.statsLoading = true;
    state.statsError = "";
    try {
      const data = (await api("/admin/stats")) as StatsResponse | AdminErrorResponse;
      if (!isOkResponse(data)) {
        state.statsError = adminErrorMessage(data, at, "load_failed");
      } else {
        state.stats = unwrap(data);
      }
    } catch (e: unknown) {
      state.statsError = e instanceof Error ? e.message : String(e);
    } finally {
      state.statsLoading = false;
    }
  }

  async function triggerSync(): Promise<void> {
    if (state.syncBusy) return;

    state.syncBusy = true;
    try {
      const res = (await api("/admin/sync", { method: "POST" })) as
        | SyncResponse
        | AdminErrorResponse;
      if (isOkResponse(res)) {
        onToast(at("sync_started", {}, "Синхронизация запущена"));
        await loadStats();
      } else {
        onToast(adminErrorMessage(res, at, at("sync_error", {}, "Ошибка синхронизации")));
      }
    } finally {
      state.syncBusy = false;
    }
  }

  return Object.assign(state, {
    loadStats,
    triggerSync,
  });
}
