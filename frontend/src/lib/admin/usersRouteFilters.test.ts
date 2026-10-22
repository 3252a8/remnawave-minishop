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
      usersTariffFilter: "all",
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
      "unmapped_tariff",
    ]) {
      expect(readUsersRouteFilters(`?users_filter=${filter}`).usersFilter).toBe(filter);
    }
    expect(readUsersRouteFilters("?users_filter=PAID").usersFilter).toBe("paid");
  });

  it("round trips exact tariff keys without changing case or losing other filters", () => {
    const filters = {
      ...DEFAULT_USERS_ROUTE_FILTERS,
      usersFilter: "active_subscription" as const,
      usersTariffFilter: "tariff:Family / Annual+2026" as const,
    };
    const params = writeUsersRouteFilters("?lang=ru", filters);
    expect(readUsersRouteFilters(params)).toEqual(filters);
    expect(params.get("lang")).toBe("ru");
    expect(writeUsersRouteFilters(params, DEFAULT_USERS_ROUTE_FILTERS).toString()).toBe("lang=ru");
  });

  it("accepts trial and missing-plan filters but rejects an empty tariff key", () => {
    for (const filter of ["trial", "no_subscription", "no_tariff"]) {
      expect(readUsersRouteFilters(`?users_tariff=${filter}`).usersTariffFilter).toBe(filter);
    }
    for (const filter of ["tariff:", "tariff:   ", "unknown"]) {
      expect(normalizeUsersRouteFilters({ usersTariffFilter: filter }).usersTariffFilter).toBe(
        "all"
      );
    }
  });
});
