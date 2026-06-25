import { describe, expect, it, vi } from "vitest";

import { createWebappSessionActions } from "./webappSessionActions.js";

function makeActions(overrides = {}) {
  const state = {
    csrfToken: "",
    token: "",
  };
  const storage = {
    clearManualLogoutFlag: vi.fn(),
    clearStoredToken: vi.fn(),
    isManuallyLoggedOut: vi.fn(() => false),
    markManualLogout: vi.fn(),
    readCookie: vi.fn(() => "cookie-csrf"),
  };
  const deps = {
    csrfCookieName: "csrf",
    isMock: () => false,
    manualLogoutFlagKey: "manual",
    setCsrfToken: vi.fn((nextToken) => {
      state.csrfToken = nextToken;
    }),
    setToken: vi.fn((nextToken) => {
      state.token = nextToken;
    }),
    storage,
    ...overrides.deps,
  };
  return {
    actions: createWebappSessionActions(deps),
    deps,
    state,
    storage,
  };
}

describe("createWebappSessionActions", () => {
  it("sets token state and reads csrf from the cookie fallback", () => {
    const { actions, state, storage } = makeActions();

    actions.setToken("jwt");

    expect(state).toEqual({ csrfToken: "cookie-csrf", token: "jwt" });
    expect(storage.clearManualLogoutFlag).toHaveBeenCalledWith("manual");
    expect(storage.readCookie).toHaveBeenCalledWith("csrf");
    expect(storage.clearStoredToken).toHaveBeenCalledOnce();
  });

  it("uses the explicit csrf token and keeps stored token in mock mode", () => {
    const { actions, state, storage } = makeActions({
      deps: { isMock: () => true },
    });

    actions.setToken("jwt", "explicit-csrf");

    expect(state).toEqual({ csrfToken: "explicit-csrf", token: "jwt" });
    expect(storage.readCookie).not.toHaveBeenCalled();
    expect(storage.clearStoredToken).not.toHaveBeenCalled();
  });

  it("clears token state and persisted token", () => {
    const { actions, state, storage } = makeActions();
    state.csrfToken = "csrf";
    state.token = "jwt";

    actions.clearToken();

    expect(state).toEqual({ csrfToken: "", token: "" });
    expect(storage.clearStoredToken).toHaveBeenCalledOnce();
  });

  it("delegates manual logout operations to storage", () => {
    const { actions, storage } = makeActions();
    storage.isManuallyLoggedOut.mockReturnValue(true);

    actions.markManualLogout();
    actions.clearManualLogoutFlag();

    expect(actions.isManuallyLoggedOut()).toBe(true);
    expect(storage.markManualLogout).toHaveBeenCalledWith("manual");
    expect(storage.clearManualLogoutFlag).toHaveBeenCalledWith("manual");
    expect(storage.isManuallyLoggedOut).toHaveBeenCalledWith("manual");
  });
});
