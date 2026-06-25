type SupportUnreadStore = {
  hydrateUnread: (count: unknown) => unknown;
  refreshUnread: () => unknown;
  startPolling: (options?: Record<string, unknown>) => unknown;
};

export type HydrateSupportUnreadInput = {
  supportEnabled: boolean;
  unreadCount: unknown;
};

/**
 * Seeds the support unread badge after `/me` resolves: a count present on the payload hydrates
 * directly, otherwise a background refresh is kicked. Either way background polling starts. Skipped
 * entirely when support is disabled. Mirrors the original `loadData` branch order.
 */
export function createSupportUnreadHydration(supportStore: SupportUnreadStore) {
  function hydrateSupportUnread({ supportEnabled, unreadCount }: HydrateSupportUnreadInput): void {
    if (!supportEnabled) return;
    if (typeof unreadCount !== "undefined") {
      supportStore.hydrateUnread(unreadCount);
    } else {
      void supportStore.refreshUnread();
    }
    supportStore.startPolling({ includeList: false });
  }

  return { hydrateSupportUnread };
}
