import { describe, expect, it } from "vitest";

import { miniAppPathFromSearch, miniAppPathFromStartParam } from "./miniAppStartRoute.js";

describe("Mini App start routes", () => {
  it.each([
    ["admin_ticket_42", "/admin/support/42"],
    ["admin_user_100200300", "/admin/users/100200300"],
    ["admin_user_-42", "/admin/users/-42"],
    ["ticket_7", "/support/7"],
    ["plan_standard__months_3__traffic_200", "/checkout"],
    ["plans", "/plans"],
    ["invite", "/invite"],
    ["partner", "/partner"],
    ["Support", "/support"],
    ["devices", "/devices"],
    ["home", "/home"],
  ])("maps %s to %s", (startParam, expected) => {
    expect(miniAppPathFromStartParam(startParam)).toBe(expected);
  });

  it("ignores unrelated and malformed start parameters", () => {
    expect(miniAppPathFromStartParam("promo_SAVE20")).toBeNull();
    expect(miniAppPathFromStartParam("admin_ticket_bad")).toBeNull();
  });

  it("never routes a bare section into the admin panel", () => {
    // Section payloads travel in links authored for customers; admin deep
    // links keep their own admin_* prefixes.
    expect(miniAppPathFromStartParam("admin")).toBeNull();
  });

  it("prefers the Telegram launch parameter", () => {
    expect(miniAppPathFromSearch("?startapp=ticket_1&tgWebAppStartParam=admin_ticket_42")).toBe(
      "/admin/support/42"
    );
  });
});
