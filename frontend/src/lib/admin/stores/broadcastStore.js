import { writable } from "svelte/store";

export function createBroadcastStore({ api, onToast, at }) {
  const COUNTS_CACHE_TTL_MS = 30_000;
  const COUNTS_DISPLAY_CACHE_TTL_MS = 5 * 60_000;
  const COUNTS_STORAGE_KEY = "remnawave-admin:broadcast-audience-counts";
  let countsPromise = null;
  const cachedCounts = readStoredCounts();

  const state = writable({
    broadcastTarget: "all",
    broadcastText: "",
    broadcastBusy: false,
    broadcastResult: null,
    broadcastCounts: cachedCounts?.counts || null,
    broadcastCountsLoading: false,
    broadcastCountsLoadedAt: cachedCounts?.loadedAt || 0,
  });

  const BROADCAST_TARGET_OPTIONS = [
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

  function countsAreFresh(stateSnapshot) {
    return (
      stateSnapshot.broadcastCounts &&
      Date.now() - Number(stateSnapshot.broadcastCountsLoadedAt || 0) < COUNTS_CACHE_TTL_MS
    );
  }

  function readStoredCounts() {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return null;
      const raw = window.sessionStorage.getItem(COUNTS_STORAGE_KEY);
      if (!raw) return null;
      const payload = JSON.parse(raw);
      const loadedAt = Number(payload?.loadedAt || 0);
      if (!payload?.counts || Date.now() - loadedAt > COUNTS_DISPLAY_CACHE_TTL_MS) return null;
      return { counts: payload.counts, loadedAt };
    } catch {
      return null;
    }
  }

  function writeStoredCounts(counts, loadedAt) {
    try {
      if (typeof window === "undefined" || !window.sessionStorage) return;
      window.sessionStorage.setItem(COUNTS_STORAGE_KEY, JSON.stringify({ counts, loadedAt }));
    } catch {
      // Ignore storage quota/privacy errors; in-memory counts still work.
    }
  }

  async function loadCounts({ force = false } = {}) {
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
        if (res?.ok && res.counts) {
          const loadedAt = Date.now();
          state.update((s) => ({
            ...s,
            broadcastCounts: res.counts,
            broadcastCountsLoadedAt: loadedAt,
          }));
          writeStoredCounts(res.counts, loadedAt);
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

  async function runBroadcast() {
    let text = "";
    let target = "";
    state.update((s) => {
      text = s.broadcastText;
      target = s.broadcastTarget;
      s.broadcastBusy = true;
      s.broadcastResult = null;
      return s;
    });

    try {
      const res = await api("/admin/broadcast", {
        method: "POST",
        body: JSON.stringify({ target, text }),
      });
      if (res?.ok) {
        state.update((s) => ({
          ...s,
          broadcastText: "",
          broadcastResult: { queued: res.queued || 0, failed: res.failed || 0 },
        }));
        onToast(at("broadcast_started", {}, "Рассылка запущена"));
      } else {
        onToast(res?.error || at("broadcast_failed", {}, "Ошибка рассылки"));
      }
    } finally {
      state.update((s) => ({ ...s, broadcastBusy: false }));
    }
  }

  function updateField(fields) {
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
