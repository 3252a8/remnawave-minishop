import { describe, expect, it, vi } from "vitest";

import { createAuthRuntime } from "./authRuntime.js";

function makeRuntime(overrides = {}) {
  const state = {
    activeTab: "",
    emailLoginDeeplinkConsumed: false,
    mode: "",
    screen: "",
  };
  const authStore = {
    clearPendingEmailCode: vi.fn(),
    requestEmailCode: vi.fn((setScreen) => {
      setScreen("email-code");
    }),
    restorePendingEmailCode: vi.fn(),
    update: vi.fn((updater) => updater({ authStatus: "old", passwordLoginFallback: true })),
  };
  const deps = {
    authStore,
    cleanDocsDemoRouteQuery: vi.fn(),
    getEmailLoginDeeplinkConsumed: () => state.emailLoginDeeplinkConsumed,
    isDocsDemo: false,
    readEmailCodeLoginDeeplink: vi.fn(() => null),
    routePathnameFromLocation: vi.fn(() => "/"),
    routePrefix: "",
    setActiveTab: vi.fn((tab) => {
      state.activeTab = tab;
    }),
    setEmailLoginDeeplinkConsumed: vi.fn((consumed) => {
      state.emailLoginDeeplinkConsumed = consumed;
    }),
    setMode: vi.fn((mode) => {
      state.mode = mode;
    }),
    setScreen: vi.fn((screen) => {
      state.screen = screen;
    }),
    syncPasswordLoginPath: vi.fn(),
    tick: vi.fn(async () => {}),
    ...overrides.deps,
  };
  return { authStore, deps, runtime: createAuthRuntime(deps), state };
}

describe("createAuthRuntime", () => {
  it("toggles password login mode and syncs the route", () => {
    const { authStore, deps, runtime } = makeRuntime({
      deps: { isDocsDemo: true, routePrefix: "/demo/runtime" },
    });

    runtime.setPasswordLoginMode(true, true);

    expect(authStore.update).toHaveBeenCalledWith(expect.any(Function));
    expect(authStore.update.mock.results[0].value).toMatchObject({
      authIsError: false,
      authStatus: "",
      passwordLoginFallback: false,
      passwordLoginMode: true,
    });
    expect(deps.syncPasswordLoginPath).toHaveBeenCalledWith({
      cleanDocsDemoRouteQuery: deps.cleanDocsDemoRouteQuery,
      enabled: true,
      isDocsDemo: true,
      replace: true,
      routePrefix: "/demo/runtime",
    });
  });

  it("starts email-code login from deeplink only once", async () => {
    const { authStore, deps, runtime, state } = makeRuntime({
      deps: { readEmailCodeLoginDeeplink: vi.fn(() => "user@example.test") },
    });

    await runtime.startEmailCodeLoginFromDeeplink();
    await runtime.startEmailCodeLoginFromDeeplink();

    expect(deps.setEmailLoginDeeplinkConsumed).toHaveBeenCalledOnce();
    expect(authStore.clearPendingEmailCode).toHaveBeenCalledOnce();
    expect(authStore.requestEmailCode).toHaveBeenCalledOnce();
    expect(state.screen).toBe("email-code");
  });

  it("shows login and restores pending email state", () => {
    const { authStore, deps, runtime, state } = makeRuntime({
      deps: { routePathnameFromLocation: vi.fn(() => "/login/password") },
    });

    runtime.showLogin();

    expect(state.mode).toBe("login");
    expect(state.screen).toBe("login");
    expect(state.activeTab).toBe("home");
    expect(deps.syncPasswordLoginPath).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true, replace: true })
    );
    expect(authStore.restorePendingEmailCode).toHaveBeenCalledWith(deps.setScreen);
  });

  it("submits email code on Enter only", () => {
    const { authStore, runtime } = makeRuntime();
    const enterEvent = { key: "Enter", preventDefault: vi.fn() };
    const escapeEvent = { key: "Escape", preventDefault: vi.fn() };

    runtime.submitEmailOnEnter(escapeEvent);
    runtime.submitEmailOnEnter(enterEvent);

    expect(escapeEvent.preventDefault).not.toHaveBeenCalled();
    expect(enterEvent.preventDefault).toHaveBeenCalledOnce();
    expect(authStore.requestEmailCode).toHaveBeenCalledOnce();
  });
});
