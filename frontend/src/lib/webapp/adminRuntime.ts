import { createAdminBundle } from "./adminBundle.js";
import { adminPayloadHasFrontendReloadChange } from "./adminPersistedSettings.js";

type WebappRecord = Record<string, unknown>;

type AdminBundleApi = WebappRecord | null;
type AdminPersistOptions = {
  updates?: Record<string, unknown>;
  deletes?: string[];
  reloadFrontend?: boolean;
  deferFrontendReload?: boolean;
};

type AdminRuntimeDeps = {
  fetchI18nScope: (scope: string) => Promise<WebappRecord | null>;
  getAdminAssets: () => { adminCssAsset?: unknown; adminJsAsset?: unknown };
  getIsMock: () => boolean;
  getShouldPrefetch: () => boolean;
  invalidateTariffOptionCaches: () => void;
  loadData: (options?: WebappRecord) => Promise<unknown>;
  mergeMessages: (messages: unknown) => void;
  reloadWindow: () => void;
  resetInstallGuides: () => void;
  setBundleState: (api: AdminBundleApi, error: string) => void;
};

export function createAdminRuntime({
  fetchI18nScope,
  getAdminAssets,
  getIsMock,
  getShouldPrefetch,
  invalidateTariffOptionCaches,
  loadData,
  mergeMessages,
  reloadWindow,
  resetInstallGuides,
  setBundleState,
}: AdminRuntimeDeps) {
  let adminI18nLoaded = false;
  let adminI18nPromise: Promise<unknown> | null = null;

  async function refreshI18nScope(scope: string) {
    if (getIsMock()) return;
    try {
      const payload = await fetchI18nScope(scope);
      if (payload?.ok && payload.i18n) mergeMessages(payload.i18n);
      if (scope === "admin") adminI18nLoaded = true;
    } catch (_error) {
      void _error;
    }
  }

  function ensureI18nScope(scope: string) {
    if (getIsMock() || scope !== "admin" || adminI18nLoaded) return Promise.resolve();
    if (adminI18nPromise) return adminI18nPromise;
    adminI18nPromise = refreshI18nScope("admin").finally(() => {
      adminI18nPromise = null;
    });
    return adminI18nPromise;
  }

  const adminBundle = createAdminBundle({
    ensureI18nScope: () => ensureI18nScope("admin"),
    getAssets: getAdminAssets,
    shouldPrefetch: getShouldPrefetch,
  });

  function syncBundleState() {
    setBundleState(adminBundle.getApi(), adminBundle.getError());
  }

  function scheduleAdminAssetsPrefetch(adminAllowed = true) {
    adminBundle.schedulePrefetch(adminAllowed);
  }

  function cancelAdminAssetsPrefetch() {
    adminBundle.cancelPrefetch();
  }

  async function ensureAdminBundle() {
    try {
      return await adminBundle.ensure();
    } finally {
      syncBundleState();
    }
  }

  function destroyAdminMount() {
    adminBundle.destroyMount();
  }

  function syncAdminMount({
    props,
    shouldMount,
    target,
  }: {
    props: WebappRecord;
    shouldMount: boolean;
    target: HTMLElement | null;
  }) {
    if (shouldMount && target) {
      adminBundle.mount(target, props);
      syncBundleState();
      return;
    }
    destroyAdminMount();
  }

  async function handleAdminPersistedSaved(options: AdminPersistOptions = {}) {
    invalidateTariffOptionCaches();
    resetInstallGuides();
    try {
      await loadData({ fresh: true, preserveView: true });
    } catch {
      // Admin save already succeeded; a later full refresh will pick up new settings or catalog.
    }
    const shouldReloadFrontend =
      options.reloadFrontend === true ||
      (!options.deferFrontendReload && adminPayloadHasFrontendReloadChange(options));
    if (shouldReloadFrontend) reloadWindow();
  }

  async function handleAdminTranslationsSaved(options: AdminPersistOptions = {}) {
    adminI18nLoaded = false;
    await Promise.all([refreshI18nScope("webapp"), refreshI18nScope("admin")]);
    await handleAdminPersistedSaved({ ...options, deferFrontendReload: true });
  }

  return {
    cancelAdminAssetsPrefetch,
    destroyAdminMount,
    ensureAdminBundle,
    ensureI18nScope,
    handleAdminPersistedSaved,
    handleAdminTranslationsSaved,
    refreshI18nScope,
    scheduleAdminAssetsPrefetch,
    syncAdminMount,
  };
}
