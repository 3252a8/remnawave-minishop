import { describe, expect, it, vi } from "vitest";

import { createRouteSync } from "./routeSync.js";

function makeRouteSync(overrides = {}) {
  const deps = {
    cleanDocsDemoRouteQuery: vi.fn(),
    getLocation: () => ({
      hash: "",
      pathname: "/",
      protocol: "https:",
      search: "?ref=1",
      ...overrides.location,
    }),
    replaceHistoryState: vi.fn(),
    syncAppSectionPath: vi.fn(),
    ...overrides.deps,
  };
  return { deps, routeSync: createRouteSync(deps) };
}

describe("createRouteSync", () => {
  it("replaces history to the support ticket path and cleans the docs-demo query", () => {
    const { deps, routeSync } = makeRouteSync();

    routeSync.syncLoadedRoute({
      initialAdminSection: null,
      initialSupportTicketId: 7,
      section: "support",
      supportTargetPath: "/support/7",
    });

    expect(deps.replaceHistoryState).toHaveBeenCalledWith("/support/7?ref=1");
    expect(deps.cleanDocsDemoRouteQuery).toHaveBeenCalledOnce();
    expect(deps.syncAppSectionPath).not.toHaveBeenCalled();
  });

  it("does not replace history when already on the target support path", () => {
    const { deps, routeSync } = makeRouteSync({ location: { pathname: "/support/7" } });

    routeSync.syncLoadedRoute({
      initialAdminSection: null,
      initialSupportTicketId: 7,
      section: "support",
      supportTargetPath: "/support/7",
    });

    expect(deps.replaceHistoryState).not.toHaveBeenCalled();
    expect(deps.cleanDocsDemoRouteQuery).toHaveBeenCalledOnce();
    expect(deps.syncAppSectionPath).not.toHaveBeenCalled();
  });

  it("does not touch history under the file: protocol", () => {
    const { deps, routeSync } = makeRouteSync({ location: { protocol: "file:" } });

    routeSync.syncLoadedRoute({
      initialAdminSection: null,
      initialSupportTicketId: 7,
      section: "support",
      supportTargetPath: "/support/7",
    });

    expect(deps.replaceHistoryState).not.toHaveBeenCalled();
    expect(deps.cleanDocsDemoRouteQuery).toHaveBeenCalledOnce();
  });

  it("syncs the section path for non-support routes with the admin section", () => {
    const { deps, routeSync } = makeRouteSync();

    routeSync.syncLoadedRoute({
      initialAdminSection: "stats",
      initialSupportTicketId: null,
      section: "admin",
      supportTargetPath: null,
    });

    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("admin", true, "stats");
    expect(deps.replaceHistoryState).not.toHaveBeenCalled();
    expect(deps.cleanDocsDemoRouteQuery).not.toHaveBeenCalled();
  });

  it("syncs the section path when support has no deep-linked ticket", () => {
    const { deps, routeSync } = makeRouteSync();

    routeSync.syncLoadedRoute({
      initialAdminSection: null,
      initialSupportTicketId: null,
      section: "support",
      supportTargetPath: null,
    });

    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("support", true, null);
    expect(deps.replaceHistoryState).not.toHaveBeenCalled();
  });
});
