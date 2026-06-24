import { describe, expect, it, vi } from "vitest";

import { createAdminPanelActions } from "./adminPanelActions.js";

function makeActions(overrides = {}) {
  const state = {
    activeTab: "home",
    adminActiveSection: "",
    isAdmin: true,
    isFileProtocol: false,
    pathname: "/admin/users/42",
    screen: "settings",
    ...overrides.state,
  };
  const deps = {
    cancelAdminAssetsPrefetch: vi.fn(),
    clearLanguageClickGuard: vi.fn(),
    closePaymentModal: vi.fn(),
    ensureAdminBundle: vi.fn(async () => null),
    ensureI18nScope: vi.fn(async () => null),
    getAdminActiveSection: () => state.adminActiveSection,
    getRoutePathname: () => state.pathname,
    getScreen: () => state.screen,
    isAdmin: () => state.isAdmin,
    isFileProtocol: () => state.isFileProtocol,
    routePrefix: "",
    setActiveTab: vi.fn((tab) => {
      state.activeTab = tab;
    }),
    setAdminActiveSection: vi.fn((section) => {
      state.adminActiveSection = section;
    }),
    setScreen: vi.fn((screen) => {
      state.screen = screen;
    }),
    showToast: vi.fn(),
    syncAppSectionPath: vi.fn(),
    t: vi.fn((key) => key),
    ...overrides.deps,
  };
  return { actions: createAdminPanelActions(deps), deps, state };
}

describe("createAdminPanelActions", () => {
  it("does not open the admin panel for non-admin users", async () => {
    const { actions, deps } = makeActions({ state: { isAdmin: false } });

    await actions.openAdminPanel();

    expect(deps.clearLanguageClickGuard).not.toHaveBeenCalled();
    expect(deps.ensureAdminBundle).not.toHaveBeenCalled();
    expect(deps.syncAppSectionPath).not.toHaveBeenCalled();
  });

  it("opens the admin panel at the current admin section", async () => {
    const { actions, deps, state } = makeActions();

    await actions.openAdminPanel();

    expect(state).toMatchObject({
      activeTab: "settings",
      adminActiveSection: "users",
      screen: "admin",
    });
    expect(deps.clearLanguageClickGuard).toHaveBeenCalledOnce();
    expect(deps.closePaymentModal).toHaveBeenCalledOnce();
    expect(deps.cancelAdminAssetsPrefetch).toHaveBeenCalledOnce();
    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("admin", false, "users");
    expect(deps.ensureI18nScope).toHaveBeenCalledWith("admin");
    expect(deps.ensureAdminBundle).toHaveBeenCalledOnce();
  });

  it("rolls back to settings when admin assets fail while still on admin screen", async () => {
    const { actions, deps, state } = makeActions({
      deps: {
        ensureAdminBundle: vi.fn(async () => {
          throw new Error("boom");
        }),
      },
    });

    await actions.openAdminPanel();

    expect(state).toMatchObject({ activeTab: "settings", screen: "settings" });
    expect(deps.syncAppSectionPath).toHaveBeenLastCalledWith("settings");
    expect(deps.showToast).toHaveBeenCalledWith("wa_unavailable");
  });

  it("closes the admin panel into settings", () => {
    const { actions, deps, state } = makeActions({ state: { screen: "admin" } });

    actions.closeAdminPanel();

    expect(state).toMatchObject({ activeTab: "settings", screen: "settings" });
    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("settings");
  });

  it("syncs admin section changes only while the admin screen is active", () => {
    const { actions, deps, state } = makeActions({ state: { screen: "admin" } });

    actions.handleAdminSectionChange("PAYMENTS", 17);
    state.screen = "settings";
    actions.handleAdminSectionChange("users");

    expect(state.adminActiveSection).toBe("payments");
    expect(deps.syncAppSectionPath).toHaveBeenCalledOnce();
    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("admin", false, "payments", 17);
  });

  it("keeps in-memory section changes on file protocol without pushing history", () => {
    const { actions, deps, state } = makeActions({
      state: { isFileProtocol: true, screen: "admin" },
    });

    actions.handleAdminSectionChange("settings");

    expect(state.adminActiveSection).toBe("settings");
    expect(deps.syncAppSectionPath).not.toHaveBeenCalled();
  });
});
