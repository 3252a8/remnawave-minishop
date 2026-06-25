import { describe, expect, it, vi } from "vitest";

import {
  createPublicInstallActions,
  publicInstallFallbackSubscription,
  PUBLIC_INSTALL_PRELOAD_KEY,
} from "./publicInstallActions.js";

function makeActions(overrides = {}) {
  const state = {
    activeTab: "",
    mode: "",
    screen: "",
    subscription: null,
    token: "",
  };
  const preloadHost = {};
  const deps = {
    getOrigin: () => "https://example.test",
    getPreloadHost: () => preloadHost,
    installGuidesStore: {
      hydrate: vi.fn((_path, payload) => ({
        enabled: true,
        subscription: payload.subscription || null,
      })),
      loadPublic: vi.fn(async () => ({
        enabled: true,
        subscription: { id: 42 },
      })),
      publicPath: vi.fn((shareToken) => `/subscription-guides/public/${shareToken}`),
    },
    setActiveTab: vi.fn((tab) => {
      state.activeTab = tab;
    }),
    setMode: vi.fn((mode) => {
      state.mode = mode;
    }),
    setPublicInstallSubscription: vi.fn((subscription) => {
      state.subscription = subscription;
    }),
    setPublicInstallToken: vi.fn((token) => {
      state.token = token;
    }),
    setScreen: vi.fn((screen) => {
      state.screen = screen;
    }),
    ...overrides.deps,
  };
  return {
    actions: createPublicInstallActions(deps),
    deps,
    preloadHost,
    state,
  };
}

describe("publicInstallFallbackSubscription", () => {
  it("builds the share subscription fallback", () => {
    expect(publicInstallFallbackSubscription("abc", "https://example.test")).toEqual({
      install_share_token: "abc",
      share_url: "https://example.test/s/abc",
    });
  });

  it("keeps an empty share url without a browser origin", () => {
    expect(publicInstallFallbackSubscription("abc")).toEqual({
      install_share_token: "abc",
      share_url: "",
    });
  });
});

describe("createPublicInstallActions", () => {
  it("hydrates public guides from a matching preload and clears it", async () => {
    const { actions, deps, preloadHost } = makeActions();
    const payload = { subscription: { id: 7 } };
    preloadHost[PUBLIC_INSTALL_PRELOAD_KEY] = {
      path: "/subscription-guides/public/share",
      promise: Promise.resolve(payload),
    };

    await expect(actions.loadPublicInstallGuides("share")).resolves.toEqual({
      enabled: true,
      subscription: payload.subscription,
    });

    expect(deps.installGuidesStore.hydrate).toHaveBeenCalledWith(
      "/subscription-guides/public/share",
      payload
    );
    expect(deps.installGuidesStore.loadPublic).not.toHaveBeenCalled();
    expect(preloadHost[PUBLIC_INSTALL_PRELOAD_KEY]).toBeNull();
  });

  it("loads public guides when preload is absent or empty", async () => {
    const { actions, deps, preloadHost } = makeActions();
    preloadHost[PUBLIC_INSTALL_PRELOAD_KEY] = {
      path: "/subscription-guides/public/share",
      promise: Promise.resolve(null),
    };

    await actions.loadPublicInstallGuides("share");

    expect(deps.installGuidesStore.hydrate).not.toHaveBeenCalled();
    expect(deps.installGuidesStore.loadPublic).toHaveBeenCalledWith("share", true);
  });

  it("enters public install mode and replaces fallback subscription from the response", async () => {
    const { actions, state } = makeActions();

    await actions.loadPublicInstall("share");

    expect(state).toEqual({
      activeTab: "home",
      mode: "publicInstall",
      screen: "install",
      subscription: { id: 42 },
      token: "share",
    });
  });
});
