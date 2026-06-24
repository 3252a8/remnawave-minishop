import { describe, expect, it, vi } from "vitest";

import { createInstallRuntime } from "./installRuntime.js";

function makeRuntime(overrides = {}) {
  const state = {
    canUseInstallGuides: false,
    mode: "",
    publicInstallSubscription: null,
    publicInstallToken: "",
    screen: "",
    ...overrides.state,
  };
  const deps = {
    canUseInstallGuides: () => state.canUseInstallGuides,
    getOrigin: () => "https://example.test",
    getPreloadHost: () => null,
    goInstall: vi.fn(),
    installGuidesStore: {
      hydrate: vi.fn((_path, payload) => payload),
      loadPublic: vi.fn(async () => ({
        subscription: { connect_url: "https://example.test/loaded" },
      })),
      publicPath: vi.fn((token) => `/subscription-guides/public/${token}`),
    },
    openConnectLink: vi.fn(),
    openTrialConnectLink: vi.fn(),
    setActiveTab: vi.fn(),
    setMode: vi.fn((mode) => {
      state.mode = mode;
    }),
    setPublicInstallSubscription: vi.fn((subscription) => {
      state.publicInstallSubscription = subscription;
    }),
    setPublicInstallToken: vi.fn((token) => {
      state.publicInstallToken = token;
    }),
    setScreen: vi.fn((screen) => {
      state.screen = screen;
    }),
    ...overrides.deps,
  };
  return { deps, runtime: createInstallRuntime(deps), state };
}

describe("createInstallRuntime", () => {
  it("opens install guides when they are available", () => {
    const { deps, runtime } = makeRuntime({ state: { canUseInstallGuides: true } });

    runtime.openInstallOrConnect();
    runtime.openTrialInstallOrConnect();

    expect(deps.goInstall).toHaveBeenCalledTimes(2);
    expect(deps.openConnectLink).not.toHaveBeenCalled();
    expect(deps.openTrialConnectLink).not.toHaveBeenCalled();
  });

  it("falls back to connect actions when guides are unavailable", () => {
    const { deps, runtime } = makeRuntime();

    runtime.openInstallOrConnect();
    runtime.openTrialInstallOrConnect();

    expect(deps.openConnectLink).toHaveBeenCalledOnce();
    expect(deps.openTrialConnectLink).toHaveBeenCalledOnce();
    expect(deps.goInstall).not.toHaveBeenCalled();
  });

  it("loads public install state through the shared public install action", async () => {
    const { deps, runtime, state } = makeRuntime();

    await runtime.loadPublicInstall("share");

    expect(state.mode).toBe("publicInstall");
    expect(state.screen).toBe("install");
    expect(state.publicInstallToken).toBe("share");
    expect(deps.installGuidesStore.loadPublic).toHaveBeenCalledWith("share", true);
    expect(state.publicInstallSubscription).toEqual({
      connect_url: "https://example.test/loaded",
    });
  });
});
