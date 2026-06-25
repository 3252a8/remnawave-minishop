import { describe, expect, it } from "vitest";

import { resolvePopstateRoute } from "./appRouteLifecycle.js";

describe("resolvePopstateRoute", () => {
  it("routes public install share links before mode-specific handling", () => {
    expect(
      resolvePopstateRoute({
        fallbackAdminSection: "stats",
        mode: "app",
        pathname: "/s/0123456789abcdef0123456789abcdef",
      })
    ).toEqual({
      kind: "publicInstall",
      shareToken: "0123456789abcdef0123456789abcdef",
    });
  });

  it("requests a boot refresh when leaving public install mode", () => {
    expect(
      resolvePopstateRoute({
        fallbackAdminSection: "stats",
        mode: "publicInstall",
        pathname: "/settings",
      })
    ).toEqual({ kind: "boot" });
  });

  it("syncs login password mode from the route", () => {
    expect(
      resolvePopstateRoute({
        fallbackAdminSection: "stats",
        mode: "login",
        pathname: "/login/password",
      })
    ).toEqual({
      kind: "login",
      passwordLoginEnabled: true,
    });
  });

  it("keeps admin routes for admin users", () => {
    expect(
      resolvePopstateRoute({
        fallbackAdminSection: "stats",
        isAdmin: true,
        mode: "app",
        pathname: "/shop/admin/users/42",
        routePrefix: "/shop",
      })
    ).toEqual({
      activeTab: "settings",
      adminSection: "users",
      kind: "admin",
      section: "admin",
    });
  });

  it("falls back to available app sections and marks required loads", () => {
    expect(
      resolvePopstateRoute({
        canUseInstallGuides: true,
        fallbackAdminSection: "stats",
        isAdmin: false,
        mode: "app",
        pathname: "/install",
      })
    ).toMatchObject({
      activeTab: "home",
      kind: "section",
      loadInstallGuides: true,
      section: "install",
    });

    expect(
      resolvePopstateRoute({
        devicesEnabled: false,
        fallbackAdminSection: "stats",
        mode: "app",
        pathname: "/devices",
      })
    ).toMatchObject({
      kind: "section",
      loadDevices: false,
      section: "home",
    });
  });
});
