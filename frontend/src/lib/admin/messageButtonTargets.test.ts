import { describe, expect, it } from "vitest";

import {
  CUSTOMER_WEBAPP_SECTIONS,
  isTelegramMessageButtonLink,
  normalizeMessageButtonLink,
  withUnavailableTarget,
} from "./messageButtonTargets.js";

describe("message button targets", () => {
  it("preserves an inactive plugin target as disabled without duplicating active options", () => {
    const active = [{ value: "/extensions/sample/services", label: "Services" }];
    expect(
      withUnavailableTarget(
        active,
        "/extensions/disabled/services",
        (target) => `Unavailable: ${target}`
      )
    ).toEqual([
      ...active,
      {
        value: "/extensions/disabled/services",
        label: "Unavailable: /extensions/disabled/services",
        disabled: true,
      },
    ]);
    expect(withUnavailableTarget(active, active[0].value, () => "missing")).toBe(active);
  });
  it.each([
    ["@help_center", "https://t.me/help_center"],
    ["t.me/help_center", "https://t.me/help_center"],
    ["https://telegram.me/help_center?start=hello", "https://t.me/help_center?start=hello"],
  ])("normalizes Telegram shortcut %s", (source, expected) => {
    expect(normalizeMessageButtonLink(source)).toBe(expected);
    expect(isTelegramMessageButtonLink(source)).toBe(true);
  });

  it("keeps ordinary HTTP links and rejects unsafe protocols", () => {
    expect(normalizeMessageButtonLink(" https://example.com/docs ")).toBe(
      "https://example.com/docs"
    );
    expect(normalizeMessageButtonLink("javascript:alert(1)")).toBeNull();
    expect(normalizeMessageButtonLink("https://user:secret@example.com")).toBeNull();
  });

  it("shares the customer Web App screens without promo targets", () => {
    expect(CUSTOMER_WEBAPP_SECTIONS).toContain("plans");
    expect(CUSTOMER_WEBAPP_SECTIONS).toContain("notifications");
    expect(CUSTOMER_WEBAPP_SECTIONS).toContain("payment-history");
    expect(CUSTOMER_WEBAPP_SECTIONS).not.toContain("promo" as never);
  });
});
