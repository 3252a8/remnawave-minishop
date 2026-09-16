import { describe, expect, it } from "vitest";

import { themeReferralBonusListMode, themeTokensToInlineStyle } from "./themeStyle.js";

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
