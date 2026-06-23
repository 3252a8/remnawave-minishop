import { writable, type Writable } from "svelte/store";
import { adminErrorMessage } from "../errors.js";
import { unwrap, type ApiResponse, type PostPayload } from "../../webapp/publicApi";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type BroadcastCounts = Record<string, number>;
type BroadcastResult = { queued: number; failed: number };
type BroadcastTargetOption = { value: string; label: string };
type StoredCounts = { counts: BroadcastCounts; loadedAt: number };
type BroadcastState = {
  broadcastTarget: string;
  broadcastText: string;
  broadcastBusy: boolean;
  broadcastResult: BroadcastResult | null;
  broadcastCounts: BroadcastCounts | null;
  broadcastCountsLoading: boolean;
  broadcastCountsLoadedAt: number;
};
type BroadcastStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type BroadcastStore = Writable<BroadcastState> & {
  runBroadcast: () => Promise<void>;
  updateField: (fields: Partial<BroadcastState>) => void;
  loadCounts: (options?: { force?: boolean }) => Promise<void>;
  BROADCAST_TARGET_OPTIONS: BroadcastTargetOption[];
};

function asBroadcastCounts(value: unknown): BroadcastCounts | null {
  if (!value || typeof value !== "object") return null;
  return Object.fromEntries(
    Object.entries(value).map(([key, count]) => {
      const numericCount = Number(count);
      return [key, Number.isFinite(numericCount) ? numericCount : 0];
    })
  );
}

export function createBroadcastStore({ api, onToast, at }: BroadcastStoreOptions): BroadcastStore {
  const COUNTS_CACHE_TTL_MS = 30_000;
  const COUNTS_DISPLAY_CACHE_TTL_MS = 5 * 60_000;
  const COUNTS_STORAGE_KEY = "remnawave-admin:broadcast-audience-counts";
  let countsPromise: Promise<void> | null = null;
  const cachedCounts = readStoredCounts();

  const state: Writable<BroadcastState> = writable({
    broadcastTarget: "all",
    broadcastText: "",
    broadcastBusy: false,
    broadcastResult: null,
    broadcastCounts: cachedCounts?.counts || null,
    broadcastCountsLoading: false,
    broadcastCountsLoadedAt: cachedCounts?.loadedAt || 0,
  });

  const BROADCAST_TARGET_OPTIONS: BroadcastTargetOption[] = [
    { value: "all", label: at("broadcast_target_all", {}, "Все активные") },
    { value: "active", label: at("broadcast_target_active", {}, "С подпиской") },
    { value: "inactive", label: at("broadcast_target_inactive", {}, "Без подписки") },
    { value: "expired", label: at("broadcast_target_expired", {}, "Expired subscription") },
    {
      value: "active_never_connected",
      label: at(
        "broadcast_target_active_never_connected",
        {},
        "С подпиской, но без VPN-подключений"
      ),
    },
    {
      value: "never",
      label: at("broadcast_target_never", {}, "Без подписки и без истории"),
    },
  ];

  function countsAreFresh(stateSnapshot: BroadcastState): boolean {
    return Boolean(
      stateSnapshot.broadcastCounts &&
      Date.now() - Number(stateSnapshot.broadcastCountsLoadedAt || 0) < COUNTS_CACHE_TTL_MS
    );
  }

  function readStoredCounts(): StoredCounts | null {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return null;
      const raw = window.sessionStorage.getItem(COUNTS_STORAGE_KEY);
      if (!raw) return null;
      const payload = JSON.parse(raw);
      const loadedAt = Number(payload?.loadedAt || 0);
      const counts = asBroadcastCounts(payload?.counts);
      if (!counts || Date.now() - loadedAt > COUNTS_DISPLAY_CACHE_TTL_MS) return null;
      return { counts, loadedAt };
    } catch {
      return null;
    }
  }

  function writeStoredCounts(counts: BroadcastCounts, loadedAt: number): void {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return;
      window.sessionStorage.setItem(COUNTS_STORAGE_KEY, JSON.stringify({ counts, loadedAt }));
    } catch {
      // Ignore storage quota/privacy errors; in-memory counts still work.
    }
  }

  async function loadCounts({ force = false }: { force?: boolean } = {}): Promise<void> {
    let shouldLoad = false;
    state.update((s) => {
      if (!force && countsAreFresh(s)) return s;
      if (countsPromise || s.broadcastCountsLoading) return s;
      shouldLoad = true;
      return { ...s, broadcastCountsLoading: true };
    });

    if (!shouldLoad) return countsPromise || Promise.resolve();

    countsPromise = (async () => {
      try {
        const res = await api("/admin/broadcast/audience-counts");
        if (res?.ok) {
          const counts = asBroadcastCounts(unwrap(res).counts);
          if (!counts) return;
          const loadedAt = Date.now();
          state.update((s) => ({
            ...s,
            broadcastCounts: counts,
            broadcastCountsLoadedAt: loadedAt,
          }));
          writeStoredCounts(counts, loadedAt);
        }
      } catch {
        // Counts are advisory; ignore failures and keep existing/plain labels.
      } finally {
        state.update((s) => ({ ...s, broadcastCountsLoading: false }));
        countsPromise = null;
      }
    })();

    return countsPromise;
  }

  async function runBroadcast(): Promise<void> {
    let text = "";
    let target = "";
    state.update((s) => {
      text = s.broadcastText;
      target = s.broadcastTarget;
      return { ...s, broadcastBusy: true, broadcastResult: null };
    });

    try {
      const body = { target, text } satisfies PostPayload<"/api/admin/broadcast">;
      const res = await api("/admin/broadcast", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (res?.ok) {
        const payload = unwrap(res);
        state.update((s) => ({
          ...s,
          broadcastText: "",
          broadcastResult: { queued: payload.queued || 0, failed: payload.failed || 0 },
        }));
        onToast(at("broadcast_started", {}, "Рассылка запущена"));
      } else {
        onToast(adminErrorMessage(res, at, at("broadcast_failed", {}, "Ошибка рассылки")));
      }
    } finally {
      state.update((s) => ({ ...s, broadcastBusy: false }));
    }
  }

  function updateField(fields: Partial<BroadcastState>): void {
    state.update((s) => ({ ...s, ...fields }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    runBroadcast,
    updateField,
    loadCounts,
    BROADCAST_TARGET_OPTIONS,
  };
}
