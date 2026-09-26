import type {
  ApiClient,
  PublicSubscriptionGuidesPath,
  PublicSubscriptionGuidesResponse,
  SubscriptionGuidesPath,
  SubscriptionGuidesResponse,
} from "../publicApi";
import { recordField, recordOrNull, stringField, type WebappRecord } from "../domainTypes";
import { buildPublicSubscriptionGuidesPath, buildSubscriptionGuidesPath } from "../publicApi";
import { unwrap } from "../publicApi";
import { guideDocumentToConfig } from "../guideDocument";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type GuidesResponse =
  SubscriptionGuidesResponse | PublicSubscriptionGuidesResponse | (WebappRecord & { ok?: boolean });
type OkGuidesResponse = Extract<
  SubscriptionGuidesResponse | PublicSubscriptionGuidesResponse,
  { ok: true }
>;
type InstallGuidesState = {
  enabled: boolean;
  config: WebappRecord | null;
  source: string | null;
  subscription: WebappRecord | null;
  error: string;
  loading: boolean;
  loaded: boolean;
};
type InFlightGuides = {
  path: SubscriptionGuidesPath | PublicSubscriptionGuidesPath;
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

function isOkGuidesResponse(response: GuidesResponse): response is OkGuidesResponse {
  return response.ok === true;
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
    const payload = isOkGuidesResponse(response) ? unwrap(response) : response;
    const payloadRecord = recordField(payload);
    return {
      enabled: Boolean(payload?.enabled),
      config: guideDocumentToConfig(payloadRecord.guide_document) || recordOrNull(payload?.config),
      source: stringField(payload?.source) || null,
      subscription: payloadRecord.subscription ? recordField(payloadRecord.subscription) : null,
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

  function applyResponse(
    path: SubscriptionGuidesPath | PublicSubscriptionGuidesPath,
    response: GuidesResponse
  ) {
    const next = stateFromResponse(response);
    loadedPath = path;
    return assignState(next);
  }

  function fetchGuidesResponse(path: SubscriptionGuidesPath | PublicSubscriptionGuidesPath) {
    if (path.startsWith("/subscription-guides/public/")) {
      return api(path);
    }
    return api(buildSubscriptionGuidesPath());
  }

  async function fetchGuides(
    path: SubscriptionGuidesPath | PublicSubscriptionGuidesPath,
    force = false
  ) {
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
          stringField(recordField(error).message) ||
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
    return fetchGuides(buildSubscriptionGuidesPath(), force);
  }

  function publicPath(shareToken: string): PublicSubscriptionGuidesPath {
    return buildPublicSubscriptionGuidesPath(shareToken);
  }

  async function loadPublic(shareToken: string, force = false) {
    return fetchGuides(publicPath(shareToken), force);
  }

  function hydrate(
    path: SubscriptionGuidesPath | PublicSubscriptionGuidesPath,
    response: GuidesResponse
  ) {
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
