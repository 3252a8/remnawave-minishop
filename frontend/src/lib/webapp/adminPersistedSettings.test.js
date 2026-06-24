import { describe, expect, it } from "vitest";

import { adminPayloadHasFrontendReloadChange } from "./adminPersistedSettings.js";

describe("admin persisted settings helpers", () => {
  it("detects frontend asset changes in updates", () => {
    expect(
      adminPayloadHasFrontendReloadChange({
        updates: { WEBAPP_LOGO_URL: "https://example.test/logo.png" },
      })
    ).toBe(true);
  });

  it("detects frontend asset changes in deletes", () => {
    expect(
      adminPayloadHasFrontendReloadChange({
        deletes: ["WEBAPP_FAVICON_URL"],
      })
    ).toBe(true);
  });

  it("ignores unrelated settings", () => {
    expect(
      adminPayloadHasFrontendReloadChange({
        deletes: ["SUPPORT_URL"],
        updates: { WEBAPP_TITLE: "New title" },
      })
    ).toBe(false);
  });
});
