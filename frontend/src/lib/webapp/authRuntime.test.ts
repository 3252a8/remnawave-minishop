import { afterEach, describe, expect, it, vi } from "vitest";

import { createAuthRuntime } from "./authRuntime.js";
import { resetShellState, shellState } from "./shellState.svelte";
type TestOverrides = { [key: string]: Record<string, unknown> | undefined };

afterEach(() => vi.unstubAllGlobals());

function makeRuntime(overrides: TestOverrides = {}) {
  resetShellState({ activeTab: "", mode: "", screen: "" });
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
    isDocsDemo: false,
    readEmailCodeLoginDeeplink: vi.fn(() => null),
    routePathnameFromLocation: vi.fn(() => "/"),
    routePrefix: "",
    syncPasswordLoginPath: vi.fn(),
    tick: vi.fn(async () => {}),
    ...overrides.deps,
  };
  return { authStore, deps, runtime: createAuthRuntime(deps) };
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
    const { authStore, runtime } = makeRuntime({
      deps: { readEmailCodeLoginDeeplink: vi.fn(() => "user@example.test") },
    });

    await runtime.startEmailCodeLoginFromDeeplink();
    await runtime.startEmailCodeLoginFromDeeplink();

    expect(shellState.emailLoginDeeplinkConsumed).toBe(true);
    expect(authStore.clearPendingEmailCode).toHaveBeenCalledOnce();
    expect(authStore.requestEmailCode).toHaveBeenCalledOnce();
    expect(shellState.screen).toBe("email-code");
  });

  it("shows login and restores pending email state", () => {
    const { authStore, deps, runtime } = makeRuntime({
      deps: { routePathnameFromLocation: vi.fn(() => "/login/password") },
    });

    runtime.showLogin();

    expect(shellState.mode).toBe("login");
    expect(shellState.screen).toBe("login");
    expect(shellState.activeTab).toBe("home");
    expect(deps.syncPasswordLoginPath).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: true, replace: true })
    );
    expect(authStore.restorePendingEmailCode).toHaveBeenCalledWith(expect.any(Function));
  });

  it("submits email code on Enter only", () => {
    const { authStore, runtime } = makeRuntime();
    const enterEvent = { key: "Enter", preventDefault: vi.fn() };
    const escapeEvent = { key: "Escape", preventDefault: vi.fn() };

    runtime.submitEmailOnEnter(escapeEvent as unknown as KeyboardEvent);
    runtime.submitEmailOnEnter(enterEvent as unknown as KeyboardEvent);

    expect(escapeEvent.preventDefault).not.toHaveBeenCalled();
    expect(enterEvent.preventDefault).toHaveBeenCalledOnce();
    expect(authStore.requestEmailCode).toHaveBeenCalledOnce();
  });

  it("remembers an install destination before sign-in changes its route", () => {
    const setItem = vi.fn();
    vi.stubGlobal("window", {
      location: { pathname: "/install", search: "?platform=ios&app=client-v2" },
      sessionStorage: { setItem, removeItem: vi.fn() },
    });
    const { deps, runtime } = makeRuntime({
      deps: { routePathnameFromLocation: () => "/install" },
    });
    runtime.showLogin();
    expect(JSON.parse(setItem.mock.calls[0][1])).toMatchObject({
      pathname: "/install",
      platform: "ios",
      app: "client-v2",
    });
    expect(setItem.mock.invocationCallOrder[0]).toBeLessThan(
      deps.syncPasswordLoginPath.mock.invocationCallOrder[0]
    );
  });
});
