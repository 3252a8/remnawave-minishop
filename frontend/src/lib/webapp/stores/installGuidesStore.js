import { writable } from "svelte/store";

export function createInstallGuidesStore({ api, t, showToast }) {
  let inFlight = null;
  const state = writable({
    enabled: false,
    config: null,
    source: null,
    subscription: null,
    error: "",
    loading: false,
    loaded: false,
  });

  async function fetchGuides(path, force = false) {
    if (inFlight?.path === path) return inFlight.promise;
    let snapshot;
    state.update((s) => {
      snapshot = s;
      return s;
    });
    if (!force && snapshot?.loaded) return snapshot;
    const promise = (async () => {
      state.update((s) => ({
        ...s,
        loading: true,
        loaded: force ? false : s.loaded,
        error: "",
      }));
      try {
        const response = await api(path);
        const next = {
          enabled: Boolean(response?.enabled),
          config: response?.config || null,
          source: response?.source || null,
          subscription: response?.subscription || null,
          error: response?.error || "",
          loading: false,
          loaded: true,
        };
        state.set(next);
        return next;
      } catch (error) {
        const message =
          error?.message || t("wa_install_unavailable", {}, "Instructions unavailable");
        if (typeof showToast === "function") showToast(message);
        const next = {
          enabled: false,
          config: null,
          source: null,
          subscription: null,
          error: message,
          loading: false,
          loaded: true,
        };
        state.set(next);
        return next;
      } finally {
        inFlight = null;
      }
    })();
    inFlight = { path, promise };
    return promise;
  }

  async function load(force = false) {
    return fetchGuides("/subscription-guides", force);
  }

  async function loadPublic(shareToken, force = false) {
    const encoded = encodeURIComponent(String(shareToken || ""));
    return fetchGuides(`/subscription-guides/public/${encoded}`, force);
  }

  function reset() {
    inFlight = null;
    state.set({
      enabled: false,
      config: null,
      source: null,
      subscription: null,
      error: "",
      loading: false,
      loaded: false,
    });
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    load,
    loadPublic,
    reset,
  };
}
