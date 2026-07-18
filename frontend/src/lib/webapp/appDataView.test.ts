import { describe, expect, it } from "vitest";

import { computeAppDataView } from "./appDataView.js";

const MOCK_DATA = {
  payment_methods: [{ id: "mock-method" }],
  plans: [{ id: "mock-plan" }],
  referral: {
    bonus_details: [{ kind: "period" }],
    one_bonus_per_referee: true,
    welcome_bonus_days: 7,
  },
  settings: {
    my_devices_enabled: true,
    subscription_guides_enabled: true,
    support_tickets_enabled: true,
  },
  subscription: { active: true },
};

describe("computeAppDataView", () => {
  it("uses config brand values and falls back to mock collections", () => {
    const view = computeAppDataView({
      cfg: {
        faviconUrl: "",
        logoUrl: "/logo.png",
        title: "Panel",
      },
      data: null,
      fallbackBrandTitle: "Subscription",
      mockData: MOCK_DATA,
    });

    expect(view.brandTitle).toBe("Panel");
    expect(view.brand.logoUrl).toBe("/logo.png");
    expect(view.faviconBrand.faviconUrl).toBe("/logo.png");
    expect(view.plans).toEqual([{ id: "mock-plan" }]);
    expect(view.methods).toEqual([]);
  });

  it("prefers loaded data over mock data", () => {
    const view = computeAppDataView({
      cfg: {},
      data: {
        payment_methods: [{ id: "card" }],
        plans: [{ id: "live-plan" }],
        settings: {
          my_devices_enabled: false,
          subscription_guides_enabled: false,
          support_tickets_enabled: false,
        },
        subscription: { active: false },
      },
      fallbackBrandTitle: "Subscription",
      mockData: MOCK_DATA,
    });

    expect(view.plans).toEqual([{ id: "live-plan" }]);
    expect(view.methods).toEqual([{ id: "card" }]);
    expect(view.devicesEnabled).toBe(false);
    expect(view.installGuidesEnabled).toBe(false);
    expect(view.supportEnabled).toBe(false);
    expect(view.subscription).toEqual({ active: false });
  });

  it("keeps Stars available only inside a Telegram Mini App", () => {
    const input = {
      cfg: {},
      data: { payment_methods: [{ id: "stars" }, { id: "card" }] },
      fallbackBrandTitle: "Subscription",
      mockData: {},
    };

    expect(computeAppDataView(input).methods).toEqual([
      {
        id: "stars",
        disabled: true,
        disabled_reason: "telegram_stars_mini_app_required",
      },
      { id: "card" },
    ]);
    expect(computeAppDataView({ ...input, telegramMiniAppContext: true }).methods).toEqual([
      { id: "stars" },
      { id: "card" },
    ]);
  });

  it("treats false and string false as disabled email auth", () => {
    expect(
      computeAppDataView({
        cfg: { emailAuthEnabled: true },
        data: { settings: { email_auth_enabled: false } },
        fallbackBrandTitle: "Subscription",
        mockData: {},
      }).emailAuthEnabled
    ).toBe(false);

    expect(
      computeAppDataView({
        cfg: { emailAuthEnabled: true },
        data: { settings: { email_auth_enabled: "false" } },
        fallbackBrandTitle: "Subscription",
        mockData: {},
      }).emailAuthEnabled
    ).toBe(false);
  });

  it("normalizes missing referral fields", () => {
    const view = computeAppDataView({
      cfg: {},
      data: { referral: { welcome_bonus_days: -3 } },
      fallbackBrandTitle: "Subscription",
      mockData: {},
    });

    expect(view.referralBonusDetails).toEqual([]);
    expect(view.referralWelcomeBonusDays).toBe(0);
    expect(view.referralOneBonusPerReferee).toBe(false);
  });
});
