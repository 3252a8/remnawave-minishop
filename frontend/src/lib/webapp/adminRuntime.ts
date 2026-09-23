import { createAdminBundle } from "./adminBundle.js";

type WebappRecord = Record<string, unknown>;

type AdminBundleApi = WebappRecord | null;
type RuntimeExtensionInstaller = (bundle: {
  registerRuntimeExtensions?: (plugins: unknown[]) => void;
}) => number | null;
type AdminPersistOptions = {
  updates?: Record<string, unknown>;
  deletes?: string[];
  deferFrontendReload?: boolean;
};

type AdminRuntimeDeps = {
  loadI18nScope: (scope: "webapp" | "admin", language: string, fresh?: boolean) => Promise<void>;
  getCurrentLang: () => string;
  getAdminAssets: () => { adminCssAsset?: unknown; adminJsAsset?: unknown };
  getIsMock: () => boolean;
  getShouldPrefetch: () => boolean;
  invalidateTariffOptionCaches: () => void;
  loadData: (options?: WebappRecord) => Promise<unknown>;
  prepareRuntimeExtensions?: () => Promise<RuntimeExtensionInstaller | null>;
  resetInstallGuides: () => void;
  setBundleState: (api: AdminBundleApi, error: string) => void;
};

export function createAdminRuntime({
  loadI18nScope,
  getCurrentLang,
  getAdminAssets,
  getIsMock,
  getShouldPrefetch,
  invalidateTariffOptionCaches,
  loadData,
  prepareRuntimeExtensions,
  resetInstallGuides,
  setBundleState,
}: AdminRuntimeDeps) {
  let runtimeGeneration: number | null = null;

  async function refreshI18nScope(scope: string) {
    if (getIsMock()) return;
    try {
      await loadI18nScope(scope === "admin" ? "admin" : "webapp", getCurrentLang(), true);
    } catch (_error) {
      void _error;
    }
  }

  function ensureI18nScope(scope: string) {
    if (getIsMock() || scope !== "admin") return Promise.resolve();
    return loadI18nScope("admin", getCurrentLang());
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

  async function preloadAdminBundle() {
    try {
      return await adminBundle.ensure();
    } finally {
      syncBundleState();
    }
  }

  async function ensureAdminBundle() {
    try {
      // Fetch package descriptors while the admin bundle and translations load.
      // Install them only after the bundle is ready, before the admin mounts.
      const runtimeExtensions = prepareRuntimeExtensions?.().catch(() => null);
      const [loaded, , installRuntimeExtensions] = await Promise.all([
        adminBundle.ensure(),
        ensureI18nScope("admin"),
        runtimeExtensions,
      ]);
      const bundle = adminBundle.getApi();
      if (loaded && bundle && installRuntimeExtensions) {
        const generation = installRuntimeExtensions(bundle);
        if (generation !== null) {
          if (runtimeGeneration !== null && generation !== runtimeGeneration)
            await refreshI18nScope("admin");
          runtimeGeneration = generation;
        }
      }
      return loaded;
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

  async function handleAdminPersistedSaved(_options: AdminPersistOptions = {}) {
    invalidateTariffOptionCaches();
    resetInstallGuides();
    try {
      await loadData({ fresh: true, preserveView: true });
    } catch {
      // Admin save already succeeded; a later full refresh will pick up new settings or catalog.
    }
  }

  async function handleAdminTranslationsSaved(options: AdminPersistOptions = {}) {
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
    preloadAdminBundle,
    refreshI18nScope,
    scheduleAdminAssetsPrefetch,
    syncAdminMount,
  };
}
