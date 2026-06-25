import { describe, expect, it } from "vitest";

import {
  resolveInitialLoadRoute,
  resolveLoadedWebappRoute,
  resolveSupportLoadRoute,
} from "./appLoadFlow.js";

describe("app load flow decisions", () => {
  it("preserves the current admin section during a preserve-view refresh", () => {
    expect(
      resolveInitialLoadRoute({
        activeTab: "home",
        adminActiveSection: "users",
        fallbackAdminSection: "stats",
        mock: false,
        pathname: "/settings",
        preserveView: true,
        screen: "admin",
      })
    ).toMatchObject({
      preservedAdminSection: "users",
      preservedSection: "admin",
      routeSection: "admin",
    });
  });

  it("prefers the docs mock screen query over the path", () => {
    expect(
      resolveInitialLoadRoute({
        activeTab: "home",
        adminActiveSection: "stats",
        fallbackAdminSection: "stats",
        mock: true,
        pathname: "/",
        screen: "home",
        screenQuery: "devices",
      }).routeSection
    ).toBe("devices");
  });

  it("normalizes unavailable protected sections after payload hydration", () => {
    expect(
      resolveLoadedWebappRoute({
        fallbackAdminSection: "stats",
        payload: {
          settings: {
            my_devices_enabled: false,
            support_tickets_enabled: true,
          },
          user: { is_admin: false },
        },
        routeSection: "devices",
      }).section
    ).toBe("home");

    expect(
      resolveLoadedWebappRoute({
        fallbackAdminSection: "stats",
        payload: { settings: {}, user: { is_admin: false } },
        routeSection: "admin",
      })
    ).toMatchObject({
      activeTab: "settings",
      initialAdminSection: null,
      section: "settings",
      shouldPrefetchAdminAssets: false,
    });
  });

  it("keeps admin routes for admin users and carries the section forward", () => {
    expect(
      resolveLoadedWebappRoute({
        fallbackAdminSection: "payments",
        payload: { user: { is_admin: true } },
        preservedAdminSection: "users",
        routeSection: "admin",
      })
    ).toMatchObject({
      activeTab: "settings",
      initialAdminSection: "users",
      section: "admin",
      shouldPrefetchAdminAssets: false,
    });
  });

  it("returns the normalized support ticket target only for support routes", () => {
    expect(
      resolveSupportLoadRoute({
        pathname: "/shop/support/42",
        routePrefix: "/shop",
        section: "support",
      })
    ).toEqual({
      initialSupportTicketId: 42,
      targetPath: "/shop/support/42",
    });
    expect(
      resolveSupportLoadRoute({
        pathname: "/shop/settings",
        routePrefix: "/shop",
        section: "settings",
      })
    ).toEqual({
      initialSupportTicketId: null,
      targetPath: null,
    });
  });
});
