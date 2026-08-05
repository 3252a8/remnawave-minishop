import { describe, expect, it } from "vitest";

import { visibleReferralLinks } from "./referralLinks.js";

describe("visibleReferralLinks", () => {
  it("keeps both configured links in website-first order", () => {
    expect(
      visibleReferralLinks({
        bot_link: "https://t.me/bot?start=ref_abc",
        webapp_link: "https://app.example/ref/abc",
      })
    ).toEqual([
      {
        id: "webapp",
        labelKey: "wa_referral_webapp_link_label",
        url: "https://app.example/ref/abc",
      },
      {
        id: "telegram",
        labelKey: "wa_referral_telegram_link_label",
        url: "https://t.me/bot?start=ref_abc",
      },
    ]);
  });

  it("returns only links that the backend exposes", () => {
    expect(visibleReferralLinks({ bot_link: " https://t.me/bot?start=ref_abc " })).toEqual([
      {
        id: "telegram",
        labelKey: "wa_referral_telegram_link_label",
        url: "https://t.me/bot?start=ref_abc",
      },
    ]);
    expect(visibleReferralLinks({ bot_link: null, webapp_link: "" })).toEqual([]);
  });
});
