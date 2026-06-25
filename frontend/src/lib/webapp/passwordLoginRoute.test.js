import { describe, expect, it, vi } from "vitest";

import { isPasswordLoginPath, syncPasswordLoginPath } from "./passwordLoginRoute.js";

function makeWindow({ pathname = "/", protocol = "https:" } = {}) {
  const calls = [];
  return {
    calls,
    history: {
      pushState: vi.fn((_data, _unused, url) => calls.push(["push", url])),
      replaceState: vi.fn((_data, _unused, url) => calls.push(["replace", url])),
    },
    location: {
      hash: "#section",
      pathname,
      protocol,
      search: "?x=1",
    },
  };
}

describe("password login route", () => {
  it("detects password login paths case-insensitively", () => {
    expect(isPasswordLoginPath("/login/password")).toBe(true);
    expect(isPasswordLoginPath("/LOGIN/PASSWORD/")).toBe(true);
    expect(isPasswordLoginPath("/login")).toBe(false);
  });

  it("pushes the password route in the normal app shell", () => {
    const view = makeWindow();

    expect(
      syncPasswordLoginPath({
        enabled: true,
        getWindow: () => view,
      })
    ).toBe(true);

    expect(view.calls).toEqual([["push", "/login/password?x=1#section"]]);
  });

  it("uses replace when requested", () => {
    const view = makeWindow({ pathname: "/login/password" });

    expect(
      syncPasswordLoginPath({
        enabled: false,
        getWindow: () => view,
        replace: true,
      })
    ).toBe(true);

    expect(view.calls).toEqual([["replace", "/?x=1#section"]]);
  });

  it("uses the docs demo runtime prefix and cleans one-shot query params", () => {
    const view = makeWindow({ pathname: "/demo/runtime/login" });
    const cleanDocsDemoRouteQuery = vi.fn();

    expect(
      syncPasswordLoginPath({
        cleanDocsDemoRouteQuery,
        enabled: true,
        getWindow: () => view,
        isDocsDemo: true,
        routePrefix: "/demo/runtime",
      })
    ).toBe(true);

    expect(view.calls).toEqual([["push", "/demo/runtime/login/password?x=1#section"]]);
    expect(cleanDocsDemoRouteQuery).toHaveBeenCalledOnce();
  });

  it("does nothing for file URLs or already-current paths", () => {
    const fileView = makeWindow({ protocol: "file:" });
    const currentView = makeWindow({ pathname: "/login/password" });

    expect(syncPasswordLoginPath({ enabled: true, getWindow: () => fileView })).toBe(false);
    expect(syncPasswordLoginPath({ enabled: true, getWindow: () => currentView })).toBe(false);

    expect(fileView.calls).toEqual([]);
    expect(currentView.calls).toEqual([]);
  });
});
