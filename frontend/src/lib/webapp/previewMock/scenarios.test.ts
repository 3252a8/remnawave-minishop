import { beforeEach, describe, expect, it } from "vitest";

import { DEV_MOCK } from "./devMock.js";
import { applyDemoDataset, applyPreviewMock } from "./scenarios.js";

describe("preview mock scenarios", () => {
  beforeEach(() => {
    DEV_MOCK.data.settings.user_balance_enabled = false;
    DEV_MOCK.data.balance.enabled = false;
    DEV_MOCK.config.compactHomeEnabled = false;
    DEV_MOCK.config.serverStatusInternal = false;
    DEV_MOCK.config.serverStatusShowOnHome = false;
    DEV_MOCK.config.authProviders = ["telegram", "email"];
    DEV_MOCK.data.settings.auth_providers = ["telegram", "email"];
    applyDemoDataset();
  });

  it("keeps optional home widgets disabled in the default demo dataset", () => {
    expect(DEV_MOCK.data.settings.user_balance_enabled).toBe(false);
    expect(DEV_MOCK.data.balance.enabled).toBe(false);
    expect(DEV_MOCK.config.compactHomeEnabled).toBe(false);
    expect(DEV_MOCK.config.serverStatusInternal).toBe(false);
    expect(DEV_MOCK.config.serverStatusShowOnHome).toBe(false);
  });

  it("enables user balance only in the dedicated preset", () => {
    applyPreviewMock("user-balance");

    expect(DEV_MOCK.data.settings.user_balance_enabled).toBe(true);
    expect(DEV_MOCK.data.balance.enabled).toBe(true);
    expect(DEV_MOCK.config.compactHomeEnabled).toBe(false);
  });

  it("enables compact home only in the dedicated preset", () => {
    applyPreviewMock("compact");

    expect(DEV_MOCK.config.compactHomeEnabled).toBe(true);
    expect(DEV_MOCK.data.settings.user_balance_enabled).toBe(false);
    expect(DEV_MOCK.data.balance.enabled).toBe(false);
    expect(DEV_MOCK.config.serverStatusShowOnHome).toBe(false);
  });

  it("enables server status only in the dedicated preset", () => {
    applyPreviewMock("server-status");

    expect(DEV_MOCK.config.serverStatusInternal).toBe(true);
    expect(DEV_MOCK.config.serverStatusShowOnHome).toBe(true);
    expect(DEV_MOCK.config.compactHomeEnabled).toBe(false);
    expect(DEV_MOCK.data.settings.user_balance_enabled).toBe(false);
    expect(DEV_MOCK.data.balance.enabled).toBe(false);
  });

  it("offers Google login in the auth preset", () => {
    applyPreviewMock("auth");

    expect(DEV_MOCK.config.authProviders).toContain("google");
    expect(DEV_MOCK.data.settings.auth_providers).toContain("google");
  });
});
