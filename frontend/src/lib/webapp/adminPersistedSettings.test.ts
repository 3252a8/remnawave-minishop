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

  it("reloads the shell after the user theme mode setting changes", () => {
    expect(
      adminPayloadHasFrontendReloadChange({
        updates: { WEBAPP_USER_THEME_MODE_ENABLED: false },
      })
    ).toBe(true);
  });

  it("reloads the shell after the Home server status setting changes", () => {
    expect(
      adminPayloadHasFrontendReloadChange({
        updates: { SERVER_STATUS_SHOW_ON_HOME: true },
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
