import { createRouteSync } from "./routeSync.js";
import { createSectionDataLoader } from "./sectionDataLoader.js";
import { createSupportUnreadHydration } from "./supportUnreadHydration.js";
import { createDevicesStore } from "./stores/devicesStore";
import { createInstallGuidesStore } from "./stores/installGuidesStore";
import { createSupportStore } from "./stores/supportStore";
import type { ApiClient } from "./publicApi";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

type SectionContextDeps = {
  api: ApiClient["api"];
  t: Translate;
  showToast: (message: string) => void;
  routePrefix: string;
  cleanDocsDemoRouteQuery: () => void;
  syncAppSectionPath: (section: string, replace?: boolean) => void;
};

/**
 * Builds the "section" slice of the webapp shell: the devices / support /
 * install-guides stores plus the loaders and route-sync glue that read from
 * them. These have simple, non-circular dependencies (api/t/showToast + the
 * docs-demo route helpers), so they extract cleanly out of App.svelte.
 */
export function createWebappSectionContext({
  api,
  t,
  showToast,
  routePrefix,
  cleanDocsDemoRouteQuery,
  syncAppSectionPath,
}: SectionContextDeps) {
  const devicesStore = createDevicesStore({ api, t, showToast });
  const supportStore = createSupportStore({ api, t, showToast, routePrefix });
  const installGuidesStore = createInstallGuidesStore({ api, t, showToast });
  const { loadSectionData } = createSectionDataLoader({
    devicesStore,
    installGuidesStore,
    supportStore,
  });
  const { hydrateSupportUnread } = createSupportUnreadHydration(supportStore);
  const { syncLoadedRoute } = createRouteSync({
    cleanDocsDemoRouteQuery,
    getLocation: () => ({
      hash: window.location.hash,
      pathname: window.location.pathname,
      protocol: window.location.protocol,
      search: window.location.search,
    }),
    replaceHistoryState: (url: string) => {
      window.history.replaceState(null, "", url);
    },
    syncAppSectionPath,
  });

  return {
    devicesStore,
    supportStore,
    installGuidesStore,
    loadSectionData,
    hydrateSupportUnread,
    syncLoadedRoute,
  };
}
