import { describe, expect, it } from "vitest";

import { createDocsDemoRouter, normalizeDocsDemoRoutePath } from "./docsDemoRoutes.js";

type FakeWindowOptions = {
  href?: string;
  parentSearch?: string | null;
  pathname?: string;
  protocol?: string;
  search?: string;
};

type FakeWindow = {
  history: { replaceState(_state: unknown, _title: unknown, url: string): void };
  location: { href: string; pathname: string; protocol: string; search: string };
  parent?: unknown;
  replacedUrl: () => string;
};

const asWindow = (view: FakeWindow) => view as unknown as Window & { parent: Window };

function makeWindow({
  href = "https://example.test/demo/runtime?path=/invite&screen=admin&x=1#preview",
  parentSearch = "",
  pathname = "/demo/runtime",
  protocol = "https:",
  search = "",
}: FakeWindowOptions = {}) {
  let replacedUrl = "";
  const view: FakeWindow = {
    history: {
      replaceState(_state: unknown, _title: unknown, url: string) {
        replacedUrl = url;
      },
    },
    location: {
      href,
      pathname,
      protocol,
      search,
    },
    replacedUrl: () => replacedUrl,
  };
  view.parent = parentSearch === null ? view : { location: { search: parentSearch } };
  return view;
}

describe("docs demo routes", () => {
  it("opens a plugin launch payload at the actual page path and preserves other parameters", () => {
    const view = makeWindow({
      pathname: "/prefix/",
      search: "?startapp=ext_sample__tools__services&x=1",
      href: "https://example.test/prefix/?startapp=ext_sample__tools__services&x=1",
    });
    const router = createDocsDemoRouter({
      getWindow: () => asWindow(view),
      isDocsDemo: false,
      routePrefix: "/prefix",
    });
    expect(router.routePathnameFromLocation()).toBe("/prefix/extensions/sample__tools/services");
    expect(view.replacedUrl()).toBe(
      "/prefix/extensions/sample__tools/services?startapp=ext_sample__tools__services&x=1"
    );
  });
  it("normalizes explicit demo route paths", () => {
    expect(normalizeDocsDemoRoutePath("admin//users/")).toBe("/admin/users");
    expect(normalizeDocsDemoRoutePath(" / ")).toBe("/");
    expect(normalizeDocsDemoRoutePath("")).toBe("");
  });

  it("reads parent route params until they are consumed", () => {
    const view = makeWindow({
      parentSearch: "?screen=admin&admin_section=users",
      search: "",
    });
    const router = createDocsDemoRouter({
      getParentRouteConsumed: () => false,
      getWindow: () => asWindow(view),
      isDocsDemo: true,
    });

    expect(router.routePathnameFromLocation()).toBe("/admin/users");

    const consumedRouter = createDocsDemoRouter({
      getParentRouteConsumed: () => true,
      getWindow: () => asWindow(view),
      isDocsDemo: true,
    });

    expect(consumedRouter.routePathnameFromLocation()).toBe("/demo/runtime");
  });

  it("lets explicit path params win over screen params", () => {
    const view = makeWindow({
      search: "?path=admin//support/&screen=invite",
    });
    const router = createDocsDemoRouter({
      getWindow: () => asWindow(view),
      isDocsDemo: true,
    });

    expect(router.routePathnameFromLocation()).toBe("/admin/support");
  });

  it("syncs demo routes through the runtime prefix and cleans one-shot params", () => {
    const view = makeWindow({
      href: "https://example.test/demo/runtime?path=/invite&screen=admin&x=1#preview",
      search: "?path=/invite&screen=admin&x=1",
    });
    const calls: unknown[][] = [];
    const router = createDocsDemoRouter({
      getWindow: () => asWindow(view),
      isDocsDemo: true,
      routePrefix: "/demo/runtime",
      syncSectionPathFn: (...args: unknown[]) => calls.push(args),
    });

    router.syncAppSectionPath("admin", true, "users", 42);

    expect(calls).toEqual([["admin", true, "users", 42, "/demo/runtime"]]);
    expect(view.replacedUrl()).toBe("/demo/runtime?x=1#preview");
  });

  it("uses normal app routing outside docs demo", () => {
    const calls: unknown[][] = [];
    const router = createDocsDemoRouter({
      getWindow: () => asWindow(makeWindow()),
      isDocsDemo: false,
      routePrefix: "/demo/runtime",
      syncSectionPathFn: (...args: unknown[]) => calls.push(args),
    });

    router.syncAppSectionPath("settings");

    expect(calls).toEqual([["settings", false, null, null]]);
  });
});
