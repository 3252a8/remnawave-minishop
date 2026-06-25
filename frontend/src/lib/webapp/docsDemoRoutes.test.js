import { describe, expect, it } from "vitest";

import { createDocsDemoRouter, normalizeDocsDemoRoutePath } from "./docsDemoRoutes.js";

function makeWindow({
  href = "https://example.test/demo/runtime?path=/invite&screen=admin&x=1#preview",
  parentSearch = "",
  pathname = "/demo/runtime",
  protocol = "https:",
  search = "",
} = {}) {
  let replacedUrl = "";
  const view = {
    history: {
      replaceState(_state, _title, url) {
        replacedUrl = url;
      },
    },
    location: {
      href,
      pathname,
      protocol,
      search,
    },
  };
  view.parent = parentSearch === null ? view : { location: { search: parentSearch } };
  view.replacedUrl = () => replacedUrl;
  return view;
}

describe("docs demo routes", () => {
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
      getWindow: () => view,
      isDocsDemo: true,
    });

    expect(router.routePathnameFromLocation()).toBe("/admin/users");

    const consumedRouter = createDocsDemoRouter({
      getParentRouteConsumed: () => true,
      getWindow: () => view,
      isDocsDemo: true,
    });

    expect(consumedRouter.routePathnameFromLocation()).toBe("/demo/runtime");
  });

  it("lets explicit path params win over screen params", () => {
    const view = makeWindow({
      search: "?path=admin//support/&screen=invite",
    });
    const router = createDocsDemoRouter({
      getWindow: () => view,
      isDocsDemo: true,
    });

    expect(router.routePathnameFromLocation()).toBe("/admin/support");
  });

  it("syncs demo routes through the runtime prefix and cleans one-shot params", () => {
    const view = makeWindow({
      href: "https://example.test/demo/runtime?path=/invite&screen=admin&x=1#preview",
      search: "?path=/invite&screen=admin&x=1",
    });
    const calls = [];
    const router = createDocsDemoRouter({
      getWindow: () => view,
      isDocsDemo: true,
      routePrefix: "/demo/runtime",
      syncSectionPathFn: (...args) => calls.push(args),
    });

    router.syncAppSectionPath("admin", true, "users", 42);

    expect(calls).toEqual([["admin", true, "users", 42, "/demo/runtime"]]);
    expect(view.replacedUrl()).toBe("/demo/runtime?x=1#preview");
  });

  it("uses normal app routing outside docs demo", () => {
    const calls = [];
    const router = createDocsDemoRouter({
      getWindow: () => makeWindow(),
      isDocsDemo: false,
      routePrefix: "/demo/runtime",
      syncSectionPathFn: (...args) => calls.push(args),
    });

    router.syncAppSectionPath("settings");

    expect(calls).toEqual([["settings", false, null, null]]);
  });
});
