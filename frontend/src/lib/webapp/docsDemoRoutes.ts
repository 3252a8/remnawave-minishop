import {
  adminSectionFromPath,
  normalizeAdminSection,
  normalizeSection,
  syncSectionPath,
} from "./routes.js";

type DocsDemoRouteParams = {
  adminSection: string;
  path: string;
  screen: string;
};

type SyncSectionPath = (
  section: string,
  replace?: boolean,
  adminSection?: string | null,
  adminUserId?: string | number | null,
  routePrefix?: string
) => void;

type WindowLike = Window & {
  parent: Window;
};

export type DocsDemoRouterOptions = {
  currentSearchParams?: () => URLSearchParams;
  getParentRouteConsumed?: () => boolean;
  getWindow?: () => WindowLike;
  isDocsDemo: boolean;
  isMockEnabled?: () => boolean;
  routePrefix?: string;
  syncSectionPathFn?: SyncSectionPath;
};

const ROUTE_QUERY_KEYS = ["path", "screen", "admin_section"] as const;

export function normalizeDocsDemoRoutePath(value: unknown) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const withSlash = raw.startsWith("/") ? raw : `/${raw}`;
  return withSlash.replace(/\/{2,}/g, "/").replace(/\/+$/, "") || "/";
}

export function createDocsDemoRouter({
  currentSearchParams,
  getParentRouteConsumed = () => false,
  getWindow = () => window as WindowLike,
  isDocsDemo,
  isMockEnabled = () => false,
  routePrefix = "",
  syncSectionPathFn = syncSectionPath as SyncSectionPath,
}: DocsDemoRouterOptions) {
  const readCurrentSearchParams =
    currentSearchParams || (() => new URLSearchParams(getWindow().location.search));

  function parentSearchParams() {
    if (!isDocsDemo) return null;
    try {
      const currentWindow = getWindow();
      if (currentWindow.parent === currentWindow) return null;
      return new URLSearchParams(currentWindow.parent.location.search);
    } catch (_error) {
      return null;
    }
  }

  function routeParams(): DocsDemoRouteParams | null {
    if (!isDocsDemo) return null;
    const currentQuery = readCurrentSearchParams();
    const currentParams = {
      path: currentQuery.get("path") || "",
      screen: currentQuery.get("screen") || "",
      adminSection: currentQuery.get("admin_section") || "",
    };
    if (currentParams.path || currentParams.screen || currentParams.adminSection) {
      return currentParams;
    }
    if (getParentRouteConsumed()) return currentParams;
    const parentQuery = parentSearchParams();
    return {
      path: parentQuery?.get("path") || "",
      screen: parentQuery?.get("screen") || "",
      adminSection: parentQuery?.get("admin_section") || "",
    };
  }

  function routePathFromParams() {
    const params = routeParams();
    if (!params) return "";
    const explicitPath = normalizeDocsDemoRoutePath(params.path);
    if (explicitPath) return explicitPath;
    const section = normalizeSection(params.screen);
    if (section === "admin") {
      return `/admin/${normalizeAdminSection(params.adminSection || "stats")}`;
    }
    return params.screen ? `/${section}` : "";
  }

  function routePathnameFromLocation() {
    return routePathFromParams() || getWindow().location.pathname;
  }

  function cleanRouteQuery() {
    const currentWindow = getWindow();
    if (!isDocsDemo || currentWindow.location.protocol === "file:") return;
    const url = new URL(currentWindow.location.href);
    const changed = ROUTE_QUERY_KEYS.some((key) => url.searchParams.has(key));
    if (!changed) return;
    for (const key of ROUTE_QUERY_KEYS) url.searchParams.delete(key);
    const search = url.searchParams.toString();
    currentWindow.history.replaceState(
      null,
      "",
      `${url.pathname}${search ? `?${search}` : ""}${url.hash}`
    );
  }

  function initialAdminSectionFromLocation() {
    const currentQuery = readCurrentSearchParams();
    if (isMockEnabled() && currentQuery.get("admin_section")) {
      return normalizeAdminSection(currentQuery.get("admin_section"));
    }
    const demoRouteParams = routeParams();
    if (isMockEnabled() && demoRouteParams?.adminSection) {
      return normalizeAdminSection(demoRouteParams.adminSection);
    }
    return adminSectionFromPath(routePathnameFromLocation(), routePrefix);
  }

  function syncDocsDemoSection(
    section: string,
    replace = false,
    adminSection: string | null = null,
    adminUserId: string | number | null = null
  ) {
    if (!isDocsDemo || getWindow().location.protocol === "file:") return false;
    syncSectionPathFn(section, replace, adminSection, adminUserId, routePrefix);
    cleanRouteQuery();
    return true;
  }

  function syncAppSectionPath(
    section: string,
    replace = false,
    adminSection: string | null = null,
    adminUserId: string | number | null = null
  ) {
    if (syncDocsDemoSection(section, replace, adminSection, adminUserId)) return;
    syncSectionPathFn(section, replace, adminSection, adminUserId);
  }

  return {
    cleanRouteQuery,
    initialAdminSectionFromLocation,
    parentSearchParams,
    routePathnameFromLocation,
    syncAppSectionPath,
  };
}
