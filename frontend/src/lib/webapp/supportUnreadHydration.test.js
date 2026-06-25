import { describe, expect, it, vi } from "vitest";

import { createSupportUnreadHydration } from "./supportUnreadHydration.js";

function makeStore() {
  return {
    hydrateUnread: vi.fn(),
    refreshUnread: vi.fn(async () => {}),
    startPolling: vi.fn(),
  };
}

describe("createSupportUnreadHydration", () => {
  it("hydrates from the payload count and starts polling", () => {
    const store = makeStore();
    const { hydrateSupportUnread } = createSupportUnreadHydration(store);

    hydrateSupportUnread({ supportEnabled: true, unreadCount: 3 });

    expect(store.hydrateUnread).toHaveBeenCalledWith(3);
    expect(store.refreshUnread).not.toHaveBeenCalled();
    expect(store.startPolling).toHaveBeenCalledWith({ includeList: false });
  });

  it("hydrates a zero count without falling back to refresh", () => {
    const store = makeStore();
    const { hydrateSupportUnread } = createSupportUnreadHydration(store);

    hydrateSupportUnread({ supportEnabled: true, unreadCount: 0 });

    expect(store.hydrateUnread).toHaveBeenCalledWith(0);
    expect(store.refreshUnread).not.toHaveBeenCalled();
  });

  it("refreshes when the payload has no unread count", () => {
    const store = makeStore();
    const { hydrateSupportUnread } = createSupportUnreadHydration(store);

    hydrateSupportUnread({ supportEnabled: true, unreadCount: undefined });

    expect(store.refreshUnread).toHaveBeenCalledOnce();
    expect(store.hydrateUnread).not.toHaveBeenCalled();
    expect(store.startPolling).toHaveBeenCalledWith({ includeList: false });
  });

  it("does nothing when support is disabled", () => {
    const store = makeStore();
    const { hydrateSupportUnread } = createSupportUnreadHydration(store);

    hydrateSupportUnread({ supportEnabled: false, unreadCount: 5 });

    expect(store.hydrateUnread).not.toHaveBeenCalled();
    expect(store.refreshUnread).not.toHaveBeenCalled();
    expect(store.startPolling).not.toHaveBeenCalled();
  });
});
