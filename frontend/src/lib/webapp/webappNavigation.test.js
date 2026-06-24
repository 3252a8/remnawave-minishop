import { describe, expect, it, vi } from "vitest";

import { createWebappNavigation } from "./webappNavigation.js";

function makeNavigation(overrides = {}) {
  const state = {
    activeTab: "",
    screen: "",
  };
  const deps = {
    canUseInstallGuides: () => true,
    closePaymentModal: vi.fn(),
    devicesEnabled: () => true,
    loadDevices: vi.fn(),
    loadInstallGuides: vi.fn(),
    loadSupport: vi.fn(),
    openConnectLink: vi.fn(),
    setActiveTab: vi.fn((tab) => {
      state.activeTab = tab;
    }),
    setScreen: vi.fn((screen) => {
      state.screen = screen;
    }),
    supportEnabled: () => true,
    syncSectionPath: vi.fn(),
    ...overrides,
  };
  return { deps, navigation: createWebappNavigation(deps), state };
}

describe("createWebappNavigation", () => {
  it("navigates to ordinary sections", () => {
    const { deps, navigation, state } = makeNavigation();

    navigation.goInvite();

    expect(deps.closePaymentModal).toHaveBeenCalledOnce();
    expect(state).toEqual({ activeTab: "invite", screen: "invite" });
    expect(deps.syncSectionPath).toHaveBeenCalledWith("invite");
  });

  it("opens the connect link instead of install guides when guides are unavailable", () => {
    const { deps, navigation } = makeNavigation({ canUseInstallGuides: () => false });

    expect(navigation.goInstall()).toBe(false);

    expect(deps.openConnectLink).toHaveBeenCalledOnce();
    expect(deps.loadInstallGuides).not.toHaveBeenCalled();
    expect(deps.closePaymentModal).not.toHaveBeenCalled();
  });

  it("loads install guides after entering the install screen", () => {
    const { deps, navigation, state } = makeNavigation();

    expect(navigation.goInstall()).toBe(true);

    expect(state).toEqual({ activeTab: "home", screen: "install" });
    expect(deps.syncSectionPath).toHaveBeenCalledWith("install");
    expect(deps.loadInstallGuides).toHaveBeenCalledOnce();
  });

  it("guards unavailable devices and support sections", () => {
    const disabledDevices = makeNavigation({ devicesEnabled: () => false });
    const disabledSupport = makeNavigation({ supportEnabled: () => false });

    expect(disabledDevices.navigation.goDevices()).toBe(false);
    expect(disabledSupport.navigation.goSupport()).toBe(false);

    expect(disabledDevices.deps.loadDevices).not.toHaveBeenCalled();
    expect(disabledSupport.deps.loadSupport).not.toHaveBeenCalled();
  });

  it("runs section side effects after entering devices and support", () => {
    const { deps, navigation } = makeNavigation();

    expect(navigation.goDevices()).toBe(true);
    expect(navigation.goSupport()).toBe(true);

    expect(deps.loadDevices).toHaveBeenCalledOnce();
    expect(deps.loadSupport).toHaveBeenCalledOnce();
  });
});
