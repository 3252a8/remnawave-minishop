import { writable } from "svelte/store";
import type {
  ApiClient,
  PublicSubscriptionGuidesResponse,
  SubscriptionGuidesResponse,
} from "../publicApi";
import { unwrap } from "../publicApi";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type GuidesResponse =
  | SubscriptionGuidesResponse
  | PublicSubscriptionGuidesResponse
  | (Record<string, unknown> & { ok?: boolean });
type GuidesPath = "/subscription-guides" | `/subscription-guides/public/${string}`;
type InstallGuidesState = {
  enabled: boolean;
  config: Record<string, unknown> | null;
  source: string | null;
  subscription: Record<string, unknown> | null;
  error: string;
  loading: boolean;
  loaded: boolean;
};
type InFlightGuides = {
  path: GuidesPath;
  promise: Promise<InstallGuidesState>;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : null;
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function createInstallGuidesStore({
  api,
  t,
  showToast,
}: {
  api: ApiClient["api"];
  t: Translate;
  showToast: (message: string) => void;
}) {
  let inFlight: InFlightGuides | null = null;
  let loadedPath = "";
  const state = writable<InstallGuidesState>({
    enabled: false,
    config: null,
    source: null,
    subscription: null,
    error: "",
    loading: false,
    loaded: false,
  });

  function stateFromResponse(response: GuidesResponse): InstallGuidesState {
    const payload =
      response.ok === true ? unwrap(response as GuidesResponse & { ok: boolean }) : response;
    return {
      enabled: Boolean(payload?.enabled),
      config: recordOrNull(payload?.config),
      source: stringField(payload?.source) || null,
      subscription: payload?.subscription ? asRecord(payload.subscription) : null,
      error: stringField(payload?.error),
      loading: false,
      loaded: true,
    };
  }

  function applyResponse(path: GuidesPath, response: GuidesResponse) {
    const next = stateFromResponse(response);
    loadedPath = path;
    state.set(next);
    return next;
  }

  function fetchGuidesResponse(path: GuidesPath) {
    if (path.startsWith("/subscription-guides/public/")) {
      return api(path as "/subscription-guides/public/{share_token}");
    }
    return api("/subscription-guides");
  }

  async function fetchGuides(path: GuidesPath, force = false) {
    if (inFlight?.path === path) return inFlight.promise;
    let snapshot: InstallGuidesState | undefined;
    state.update((s) => {
      snapshot = s;
      return s;
    });
    if (!force && snapshot?.loaded && loadedPath === path) return snapshot;
    const promise = (async () => {
      state.update((s) => ({
        ...s,
        loading: true,
        loaded: force ? false : s.loaded,
        error: "",
      }));
      try {
        const response = await fetchGuidesResponse(path);
        const next = applyResponse(path, response);
        return next;
      } catch (error: unknown) {
        const message =
          stringField(asRecord(error).message) ||
          t("wa_install_unavailable", {}, "Instructions unavailable");
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
        loadedPath = path;
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

  function publicPath(shareToken: string): `/subscription-guides/public/${string}` {
    const encoded = encodeURIComponent(String(shareToken || ""));
    return `/subscription-guides/public/${encoded}`;
  }

  async function loadPublic(shareToken: string, force = false) {
    return fetchGuides(publicPath(shareToken), force);
  }

  function hydrate(path: GuidesPath, response: GuidesResponse) {
    inFlight = null;
    return applyResponse(path, response);
  }

  function reset() {
    inFlight = null;
    loadedPath = "";
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
    hydrate,
    publicPath,
    reset,
  };
}
