import {
  appendPrefetchOnce,
  appendScriptWithFallback,
  appendStylesheetWithFallback,
  resolveWebappAssetPath,
} from "./assetLoader";

type AdminBundleApi = {
  mount(target: HTMLElement, props: Record<string, unknown>): AdminMountHandle;
};
type AdminMountHandle = {
  destroy?: () => void;
  update?: (props: Record<string, unknown>) => void;
};
type AdminAssets = {
  adminCssAsset?: unknown;
  adminJsAsset?: unknown;
};
type WindowWithAdminBundle = Window & {
  SubscriptionWebAppAdmin?: AdminBundleApi;
  requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
};

function errorMessage(error: unknown, fallback: string) {
  return error && typeof error === "object" && "message" in error
    ? String(error.message || fallback)
    : fallback;
}

export function createAdminBundle({
  ensureI18nScope,
  getAssets,
  shouldPrefetch,
}: {
  ensureI18nScope: () => Promise<unknown> | unknown;
  getAssets: () => AdminAssets;
  shouldPrefetch: () => boolean;
}) {
  let bundleApi: AdminBundleApi | null = null;
  let bundlePromise: Promise<boolean> | null = null;
  let bundleError = "";
  let assetsPrefetched = false;
  let assetsPrefetchHandle: number | null = null;
  let mountHandle: AdminMountHandle | null = null;
  let mountedTarget: HTMLElement | null = null;

  function assetUrls() {
    const assets = getAssets();
    return {
      cssHref: resolveWebappAssetPath(assets.adminCssAsset, "subscription_webapp_admin.css"),
      jsSrc: resolveWebappAssetPath(assets.adminJsAsset, "subscription_webapp_admin.js"),
    };
  }

  function readBundleApi() {
    const bundle = (window as WindowWithAdminBundle).SubscriptionWebAppAdmin;
    return bundle?.mount ? bundle : null;
  }

  function getApi() {
    return bundleApi;
  }

  function getError() {
    return bundleError;
  }

  function prefetchAssets() {
    if (assetsPrefetched || bundleApi || bundlePromise) return;
    assetsPrefetched = true;
    const { cssHref, jsSrc } = assetUrls();
    appendPrefetchOnce("subscription-webapp-admin-css-prefetch", cssHref, "style");
    appendPrefetchOnce("subscription-webapp-admin-js-prefetch", jsSrc, "script");
    void ensureI18nScope();
  }

  function schedulePrefetch(adminAllowed = true) {
    if (!adminAllowed || assetsPrefetched || bundleApi || bundlePromise) return;
    if (typeof window === "undefined") return;
    const currentWindow = window as WindowWithAdminBundle;
    const run = () => {
      assetsPrefetchHandle = null;
      if (!shouldPrefetch()) return;
      prefetchAssets();
    };
    if (currentWindow.requestIdleCallback) {
      assetsPrefetchHandle = currentWindow.requestIdleCallback(run, { timeout: 3000 });
    } else {
      assetsPrefetchHandle = window.setTimeout(run, 1200);
    }
  }

  function cancelPrefetch() {
    if (assetsPrefetchHandle === null || typeof window === "undefined") return;
    const currentWindow = window as WindowWithAdminBundle;
    if (currentWindow.cancelIdleCallback) {
      currentWindow.cancelIdleCallback(assetsPrefetchHandle);
    } else {
      window.clearTimeout(assetsPrefetchHandle);
    }
    assetsPrefetchHandle = null;
  }

  async function ensure() {
    if (bundleApi) return true;
    if (bundlePromise) return bundlePromise;

    const existing = readBundleApi();
    if (existing) {
      bundleApi = existing;
      return true;
    }

    bundleError = "";
    bundlePromise = (async () => {
      const { cssHref, jsSrc } = assetUrls();
      await appendStylesheetWithFallback(
        "subscription-webapp-admin-css",
        cssHref,
        "subscription_webapp_admin.css"
      );
      await appendScriptWithFallback(
        "subscription-webapp-admin-js",
        jsSrc,
        "subscription_webapp_admin.js",
        { type: "module" }
      );
      const loaded = readBundleApi();
      if (!loaded) throw new Error("admin_bundle_missing_mount");
      bundleApi = loaded;
      return true;
    })()
      .catch((error) => {
        bundleError = errorMessage(error, "admin_bundle_load_failed");
        throw error;
      })
      .finally(() => {
        bundlePromise = null;
      });

    return bundlePromise;
  }

  function destroyMount() {
    if (!mountHandle) return;
    mountHandle.destroy?.();
    mountHandle = null;
    mountedTarget = null;
  }

  function mount(target: HTMLElement, props: Record<string, unknown>) {
    if (!bundleApi || !target) return false;
    try {
      if (mountHandle && mountedTarget === target) {
        mountHandle.update?.(props);
      } else {
        destroyMount();
        target.replaceChildren();
        mountHandle = bundleApi.mount(target, props);
        mountedTarget = target;
      }
      return true;
    } catch (error) {
      bundleError = errorMessage(error, "admin_bundle_mount_failed");
      bundleApi = null;
      destroyMount();
      return false;
    }
  }

  return {
    cancelPrefetch,
    destroyMount,
    ensure,
    getApi,
    getError,
    mount,
    schedulePrefetch,
  };
}
