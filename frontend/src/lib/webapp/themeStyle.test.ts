import { describe, expect, it } from "vitest";

import {
  themeHomeElementIsVisible,
  themeHomeElementVisibility,
  themeReferralBonusListMode,
  themeTokensToInlineStyle,
} from "./themeStyle.js";

describe("themeTokensToInlineStyle", () => {
  it("quotes the separator token as a CSS string", () => {
    expect(themeTokensToInlineStyle({ separator: "|" })).toContain('--separator:"|"');
  });

  it("keeps an empty separator so a theme can drop the separator", () => {
    expect(themeTokensToInlineStyle({ separator: "" })).toContain('--separator:""');
  });

  it("omits the separator when the theme does not define it", () => {
    expect(themeTokensToInlineStyle({ color_scheme: "dark" })).not.toContain("--separator:");
  });

  it("ignores separator values with control characters", () => {
    expect(themeTokensToInlineStyle({ separator: "a\nb" })).not.toContain("--separator:");
  });
});

describe("themeReferralBonusListMode", () => {
  it("reads the behaviour token from theme tokens", () => {
    expect(themeReferralBonusListMode({ referral_bonus_list: "collapsed" })).toBe("collapsed");
    expect(themeReferralBonusListMode({ referral_bonus_list: "EXPANDED" })).toBe("expanded");
  });

  it("falls back to plain for missing or unknown values", () => {
    expect(themeReferralBonusListMode(null)).toBe("plain");
    expect(themeReferralBonusListMode({})).toBe("plain");
    expect(themeReferralBonusListMode({ referral_bonus_list: "collapsable" })).toBe("plain");
    expect(themeReferralBonusListMode({ referral_bonus_list: 5 })).toBe("plain");
  });

  it("keeps the behaviour token out of CSS variables", () => {
    expect(themeTokensToInlineStyle({ referral_bonus_list: "collapsed" })).not.toContain(
      "referral_bonus_list"
    );
  });
});

describe("themeHomeElementVisibility", () => {
  it("normalizes every Home element through the shared visibility policy", () => {
    const visibility = themeHomeElementVisibility({
      home_subscription_period_visibility: "HIDDEN",
      home_tariff_name_visibility: "visible",
      home_balance_visibility: "auto",
      home_auto_renew_visibility: "collapsable",
    });

    expect(visibility.subscriptionPeriod).toBe("hidden");
    expect(visibility.tariffName).toBe("visible");
    expect(visibility.balance).toBe("auto");
    expect(visibility.autoRenew).toBe("auto");
    expect(visibility.regularTraffic).toBe("auto");
  });

  it("lets visible override presentation heuristics without overriding availability", () => {
    expect(themeHomeElementIsVisible("auto", false, true)).toBe(false);
    expect(themeHomeElementIsVisible("visible", false, true)).toBe(true);
    expect(themeHomeElementIsVisible("visible", false, false)).toBe(false);
    expect(themeHomeElementIsVisible("hidden", true, true)).toBe(false);
  });

  it("keeps Home behaviour tokens out of CSS variables", () => {
    expect(themeTokensToInlineStyle({ home_balance_visibility: "hidden" })).not.toContain(
      "home_balance_visibility"
    );
  });
});
