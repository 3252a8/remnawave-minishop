import { beforeEach, describe, expect, it } from "vitest";

import { DEV_MOCK } from "./devMock.js";
import { applyDemoDataset, applyPreviewMock } from "./scenarios.js";

describe("preview mock scenarios", () => {
  beforeEach(() => {
    DEV_MOCK.data.settings.user_balance_enabled = false;
    DEV_MOCK.config.authProviders = ["telegram", "email"];
    DEV_MOCK.data.settings.auth_providers = ["telegram", "email"];
    applyDemoDataset();
  });

  it("keeps user balance disabled in the default demo dataset", () => {
    expect(DEV_MOCK.data.settings.user_balance_enabled).toBe(false);
  });

  it("enables user balance only in the dedicated preset", () => {
    applyPreviewMock("user-balance");

    expect(DEV_MOCK.data.settings.user_balance_enabled).toBe(true);
  });

  it("offers Google login in the auth preset", () => {
    applyPreviewMock("auth");

    expect(DEV_MOCK.config.authProviders).toContain("google");
    expect(DEV_MOCK.data.settings.auth_providers).toContain("google");
  });
});
