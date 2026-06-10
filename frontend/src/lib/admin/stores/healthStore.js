import { writable } from "svelte/store";

export function createHealthStore({ api }) {
  const state = writable({
    alerts: [],
    checkedAt: null,
    healthLoading: false,
    healthError: "",
  });

  async function loadHealth({ refresh = false } = {}) {
    state.update((s) => ({ ...s, healthLoading: true, healthError: "" }));
    try {
      const data = await api(`/admin/health${refresh ? "?refresh=1" : ""}`);
      if (!data?.ok) {
        state.update((s) => ({ ...s, healthError: data?.error || "load_failed" }));
      } else {
        state.update((s) => ({
          ...s,
          alerts: Array.isArray(data.alerts) ? data.alerts : [],
          checkedAt: data.checked_at || null,
        }));
      }
    } catch (e) {
      state.update((s) => ({ ...s, healthError: e?.message || String(e) }));
    } finally {
      state.update((s) => ({ ...s, healthLoading: false }));
    }
  }

  return {
    subscribe: state.subscribe,
    loadHealth,
  };
}
