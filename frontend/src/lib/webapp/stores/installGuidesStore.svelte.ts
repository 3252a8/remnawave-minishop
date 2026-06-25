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

const initialInstallGuidesState = (): InstallGuidesState => ({
  enabled: false,
  config: null,
  source: null,
  subscription: null,
  error: "",
  loading: false,
  loaded: false,
});

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
  const state = $state<InstallGuidesState>(initialInstallGuidesState());

  function stateFromResponse(response: GuidesResponse): InstallGuidesState {
    const payload =
      response.ok === true ? unwrap(response as GuidesResponse & { ok: boolean }) : response;
    const payloadRecord = asRecord(payload);
    return {
      enabled: Boolean(payload?.enabled),
      config: recordOrNull(payload?.config),
      source: stringField(payload?.source) || null,
      subscription: payloadRecord.subscription ? asRecord(payloadRecord.subscription) : null,
      error: stringField(payloadRecord.error),
      loading: false,
      loaded: true,
    };
  }

  function assignState(next: InstallGuidesState): InstallGuidesState {
    Object.assign(state, next);
    return state;
  }

  function patchState(patch: Partial<InstallGuidesState>): void {
    Object.assign(state, patch);
  }

  function applyResponse(path: GuidesPath, response: GuidesResponse) {
    const next = stateFromResponse(response);
    loadedPath = path;
    return assignState(next);
  }

  function fetchGuidesResponse(path: GuidesPath) {
    if (path.startsWith("/subscription-guides/public/")) {
      return api(path as "/subscription-guides/public/{share_token}");
    }
    return api("/subscription-guides");
  }

  async function fetchGuides(path: GuidesPath, force = false) {
    if (inFlight?.path === path) return inFlight.promise;
    if (!force && state.loaded && loadedPath === path) return state;
    const promise = (async () => {
      patchState({
        loading: true,
        loaded: force ? false : state.loaded,
        error: "",
      });
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
        return assignState(next);
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
    assignState(initialInstallGuidesState());
  }

  return {
    get enabled() {
      return state.enabled;
    },
    get config() {
      return state.config;
    },
    get source() {
      return state.source;
    },
    get subscription() {
      return state.subscription;
    },
    get error() {
      return state.error;
    },
    get loading() {
      return state.loading;
    },
    get loaded() {
      return state.loaded;
    },
    load,
    loadPublic,
    hydrate,
    publicPath,
    reset,
  };
}

export type InstallGuidesStore = ReturnType<typeof createInstallGuidesStore>;
