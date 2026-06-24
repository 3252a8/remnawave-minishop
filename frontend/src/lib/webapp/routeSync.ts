export type RouteSyncLocation = {
  hash: string;
  pathname: string;
  protocol: string;
  search: string;
};

export type RouteSyncDeps = {
  cleanDocsDemoRouteQuery: () => void;
  getLocation: () => RouteSyncLocation;
  replaceHistoryState: (url: string) => void;
  syncAppSectionPath: (section: string, replace?: boolean, adminSection?: string | null) => void;
};

export type SyncLoadedRouteInput = {
  initialAdminSection: string | null;
  initialSupportTicketId: number | null;
  section: string;
  supportTargetPath: string | null;
};

/**
 * Commits the freshly-resolved load route to the URL. A deep-linked support ticket replaces the
 * history entry directly (preserving the current query/hash) and cleans the docs-demo route query;
 * every other section defers to `syncAppSectionPath`. Mirrors the original `loadData` branch.
 */
export function createRouteSync({
  cleanDocsDemoRouteQuery,
  getLocation,
  replaceHistoryState,
  syncAppSectionPath,
}: RouteSyncDeps) {
  function syncLoadedRoute({
    initialAdminSection,
    initialSupportTicketId,
    section,
    supportTargetPath,
  }: SyncLoadedRouteInput): void {
    if (section === "support" && initialSupportTicketId && supportTargetPath) {
      const location = getLocation();
      if (location.protocol !== "file:" && location.pathname !== supportTargetPath) {
        replaceHistoryState(`${supportTargetPath}${location.search}${location.hash}`);
      }
      cleanDocsDemoRouteQuery();
      return;
    }
    syncAppSectionPath(section, true, initialAdminSection);
  }

  return { syncLoadedRoute };
}
