import { describe, expect, it } from "vitest";

import {
  DEFAULT_USERS_ROUTE_FILTERS,
  normalizeUsersRouteFilters,
  readUsersRouteFilters,
  writeUsersRouteFilters,
} from "./usersRouteFilters.js";

describe("usersRouteFilters", () => {
  it("reads all supported user-list filters from the query string", () => {
    expect(
      readUsersRouteFilters(
        "?users_filter=paid&users_panel_status=active&users_premium_traffic=warn"
      )
    ).toEqual({
      usersFilter: "paid",
      usersPanelStatus: "active",
      usersPremiumTraffic: "warn",
    });
  });

  it("normalizes missing and unsupported values to safe defaults", () => {
    expect(
      normalizeUsersRouteFilters({
        usersFilter: "unknown",
        usersPanelStatus: "BANNED",
        usersPremiumTraffic: null,
      })
    ).toEqual(DEFAULT_USERS_ROUTE_FILTERS);
  });

  it("keeps unrelated query parameters and omits default filters", () => {
    const params = writeUsersRouteFilters("?lang=ru&users_filter=trial", {
      ...DEFAULT_USERS_ROUTE_FILTERS,
      usersPanelStatus: "expired",
    });

    expect(params.toString()).toBe("lang=ru&users_panel_status=expired");
  });

  it("canonicalizes case and supports every dashboard counter filter", () => {
    for (const filter of [
      "active_today",
      "referred",
      "active_subscription",
      "paid",
      "free",
      "trial",
      "inactive_subscription",
      "expired_subscription",
    ]) {
      expect(readUsersRouteFilters(`?users_filter=${filter}`).usersFilter).toBe(filter);
    }
    expect(readUsersRouteFilters("?users_filter=PAID").usersFilter).toBe("paid");
  });
});
