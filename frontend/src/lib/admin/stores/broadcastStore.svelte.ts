import { adminErrorMessage } from "../errors.js";
import {
  buildAdminBroadcastAudienceCountsPath,
  buildAdminBroadcastPath,
  unwrap,
  type ApiResponse,
  type PostPayload,
} from "../../webapp/publicApi";

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
export type BroadcastState = {
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
export type BroadcastStore = BroadcastState & {
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

  const state = $state<BroadcastStore>({
    broadcastTarget: "all",
    broadcastText: "",
    broadcastBusy: false,
    broadcastResult: null,
    broadcastCounts: cachedCounts?.counts || null,
    broadcastCountsLoading: false,
    broadcastCountsLoadedAt: cachedCounts?.loadedAt || 0,
    runBroadcast,
    updateField,
    loadCounts,
    BROADCAST_TARGET_OPTIONS: [],
  });

  function updateState(updater: (snapshot: BroadcastStore) => BroadcastStore): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

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
  state.BROADCAST_TARGET_OPTIONS = BROADCAST_TARGET_OPTIONS;

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
    updateState((s) => {
      if (!force && countsAreFresh(s)) return s;
      if (countsPromise || s.broadcastCountsLoading) return s;
      shouldLoad = true;
      return { ...s, broadcastCountsLoading: true };
    });

    if (!shouldLoad) return countsPromise || Promise.resolve();

    countsPromise = (async () => {
      try {
        const res = await api(buildAdminBroadcastAudienceCountsPath());
        if (res?.ok) {
          const counts = asBroadcastCounts(unwrap(res).counts);
          if (!counts) return;
          const loadedAt = Date.now();
          updateState((s) => ({
            ...s,
            broadcastCounts: counts,
            broadcastCountsLoadedAt: loadedAt,
          }));
          writeStoredCounts(counts, loadedAt);
        }
      } catch {
        // Counts are advisory; ignore failures and keep existing/plain labels.
      } finally {
        updateState((s) => ({ ...s, broadcastCountsLoading: false }));
        countsPromise = null;
      }
    })();

    return countsPromise;
  }

  async function runBroadcast(): Promise<void> {
    const text = state.broadcastText;
    const target = state.broadcastTarget;
    updateState((s) => ({ ...s, broadcastBusy: true, broadcastResult: null }));

    try {
      const body = { target, text } satisfies PostPayload<"/api/admin/broadcast">;
      const res = await api(buildAdminBroadcastPath(), {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (res?.ok) {
        const payload = unwrap(res);
        updateState((s) => ({
          ...s,
          broadcastText: "",
          broadcastResult: { queued: payload.queued || 0, failed: payload.failed || 0 },
        }));
        onToast(at("broadcast_started", {}, "Рассылка запущена"));
      } else {
        onToast(adminErrorMessage(res, at, at("broadcast_failed", {}, "Ошибка рассылки")));
      }
    } finally {
      updateState((s) => ({ ...s, broadcastBusy: false }));
    }
  }

  function updateField(fields: Partial<BroadcastState>): void {
    updateState((s) => ({ ...s, ...fields }));
  }

  return state;
}
