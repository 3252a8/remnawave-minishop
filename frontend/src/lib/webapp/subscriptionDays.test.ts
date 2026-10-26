import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import SubscriptionDaysQuoteView from "../../webapp/payment-dialogs/SubscriptionDaysQuote.svelte";
import { createI18n } from "./i18n.js";
import {
  subscriptionDaysQuoteUsable,
  withSubscriptionDaysMethod,
  type SubscriptionDaysQuote,
} from "./subscriptionDays.js";
import ru from "../../../../locales/ru.json";
import en from "../../../../locales/en.json";

const quote: SubscriptionDaysQuote = {
  eligible: true,
  disabled_reason: null,
  days_to_charge: 7,
  current_expires_at: "2026-12-31T12:00:00Z",
  next_expires_at: "2026-12-24T12:00:00Z",
  minimum_remaining_days: 1,
  quote_token: "signed-quote",
  price_amount: 190,
  currency: "RUB",
};
const methods = [{ id: "card", name: "Card", disabled: false }];
const { t } = createI18n({ messages: { ru, en }, defaultLang: "ru" });

describe("subscription day checkout", () => {
  it("leaves ordinary checkout methods unchanged when the feature is off", () => {
    expect(withSubscriptionDaysMethod(methods, { price: 190 }, t)).toBe(methods);
  });

  it("keeps money methods and appends the server-authorized day method", () => {
    const result = withSubscriptionDaysMethod(methods, { subscription_days: quote }, t);
    expect(result[0]).toEqual(methods[0]);
    expect(result[1]).toMatchObject({
      id: "subscription_days",
      disabled: false,
      balance_supported: false,
    });
  });

  it.each([
    "subscription_required",
    "paid_subscription_required",
    "duration_required",
    "recurring_conflict",
    "price_unavailable",
    "insufficient_days",
    "package_unavailable",
  ])("explains %s without enabling payment", (reason) => {
    const result = withSubscriptionDaysMethod(
      methods,
      { subscription_days: { ...quote, eligible: false, disabled_reason: reason } },
      t
    );
    expect(result[1]).toMatchObject({
      disabled: true,
      disabled_message: t(`wa_subscription_days_${reason}`, { days: 1 }),
    });
  });

  it.each([
    { quote_token: null },
    { days_to_charge: 0 },
    { days_to_charge: 1.5 },
    { current_expires_at: "invalid" },
    { next_expires_at: "invalid" },
    { next_expires_at: "2027-01-01T12:00:00Z" },
  ])("does not enable an incomplete or inconsistent quote: %j", (patch) => {
    expect(subscriptionDaysQuoteUsable({ ...quote, ...patch })).toBe(false);
  });

  it.each(["ru", "en"])(
    "renders both server expiry dates and the device lifetime in %s",
    (language) => {
      const { t: translate } = createI18n({ messages: { ru, en }, defaultLang: language });
      const { body } = render(SubscriptionDaysQuoteView, {
        props: {
          quote,
          devices: true,
          currentLang: language,
          t: translate,
        },
      });
      expect(body).toContain(translate("wa_subscription_days_charge", { days: 7 }));
      expect(body).toContain(translate("wa_subscription_days_devices_hint"));
      expect(body).toContain("31");
      expect(body).toContain("24");
      expect(body).not.toContain("signed-quote");
    }
  );
});
