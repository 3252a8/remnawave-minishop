import { describe, expect, it, vi } from "vitest";

import { buildAdminPanelProps } from "./adminPanelProps.js";

const base = {
  adminActiveSection: "users",
  api: vi.fn(),
  appFaviconUrl: "/favicon.png",
  appFaviconUseCustom: true,
  appRepositoryUrl: "https://example.invalid/repo",
  appVersion: "1.2.3",
  brand: { title: "Brand" },
  brandTitle: "Brand",
  currentLang: "ru",
  fallbackAdminSection: "stats",
  languageBusy: false,
  languageOptions: [],
  onClose: vi.fn(),
  onLanguageChange: vi.fn(),
  onSectionChange: vi.fn(),
  onSettingsSaved: vi.fn(),
  onTariffsSaved: vi.fn(),
  onThemesSaved: vi.fn(),
  onToast: vi.fn(),
  onTranslationsSaved: vi.fn(),
  pathname: "/admin/users/42",
  routePrefix: "",
  screen: "admin",
  t: vi.fn(),
};

describe("buildAdminPanelProps", () => {
  it("uses the active admin section when the shell is already on admin", () => {
    expect(buildAdminPanelProps(base)).toMatchObject({
      initialSection: "users",
      initialUserId: 42,
      routePrefix: "",
    });
  });

  it("uses the route-derived fallback section before admin is mounted", () => {
    expect(
      buildAdminPanelProps({
        ...base,
        fallbackAdminSection: "payments",
        pathname: "/admin/payments/users/7",
        screen: "settings",
      })
    ).toMatchObject({
      initialPaymentUserId: 7,
      initialSection: "payments",
    });
  });

  it("preserves settings subpaths under a route prefix", () => {
    expect(
      buildAdminPanelProps({
        ...base,
        pathname: "/shop/admin/settings/payments/stripe",
        routePrefix: "/shop",
      }).initialSettingsPath
    ).toEqual(["payments", "stripe"]);
  });
});
