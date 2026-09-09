import { afterEach, describe, expect, it, vi } from "vitest";

import { createBillingDeeplinkEffects } from "./billingDeeplinkEffects.js";
import { readCheckoutPromoDeeplink } from "./deeplinks.js";
type TestOverrides = Record<string, unknown>;

function makeEffects(overrides: TestOverrides = {}) {
  const deps = {
    billingStore: {
      applyCheckoutPromo: vi.fn(),
      openPaymentModal: vi.fn(),
      openTopupModal: vi.fn(),
      setCheckoutPromoInput: vi.fn(),
    },
    readCheckoutPromoDeeplink: vi.fn(() => ""),
    readCheckoutDeeplink: vi.fn(() => null),
    readPlansDeeplink: vi.fn(() => false),
    readRenewalDeeplink: vi.fn(() => null),
    setHomeRoute: vi.fn(),
    stripCheckoutPromoQueryFromUrl: vi.fn(),
    stripCheckoutDeeplinkFromUrl: vi.fn(),
    stripRenewalLoginQueryFromUrl: vi.fn(),
    stripTopupQueryFromUrl: vi.fn(),
    ...overrides,
  };
  return { deps, effects: createBillingDeeplinkEffects(deps) };
}

const activeRegularSubscription = {
  active: true,
  tariff_key: "pro",
  can_topup_traffic: true,
  traffic_limit_bytes: 10,
};

const tariffPlans = [{ tariff_key: "pro" }];

describe("createBillingDeeplinkEffects", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the topup modal and strips the query when a topup deeplink resolves", () => {
    const { deps, effects } = makeEffects();

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "?topup=regular",
      subscription: activeRegularSubscription,
    });

    expect(deps.billingStore.openTopupModal).toHaveBeenCalledWith("regular", "card");
    expect(deps.stripTopupQueryFromUrl).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).not.toHaveBeenCalled();
    expect(deps.stripRenewalLoginQueryFromUrl).not.toHaveBeenCalled();
  });

  it("does nothing for topup when no topup deeplink is present", () => {
    const { deps, effects } = makeEffects();

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "",
      subscription: activeRegularSubscription,
    });

    expect(deps.billingStore.openTopupModal).not.toHaveBeenCalled();
    expect(deps.stripTopupQueryFromUrl).not.toHaveBeenCalled();
  });

  it("opens the renewal payment modal, syncs home route and strips the renewal query", () => {
    const { deps, effects } = makeEffects({
      readRenewalDeeplink: vi.fn(() => ({ tariffKey: "pro" })),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "?after_login=renew",
      subscription: activeRegularSubscription,
    });

    expect(deps.setHomeRoute).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
    const call = deps.billingStore.openPaymentModal.mock.calls[0];
    // tariffMode, singleTariffMode, tariffCatalog, subscription, plans, defaultMethod, options
    expect(call[0]).toBe(true);
    expect(call[1]).toBe(true);
    expect(call[5]).toBe("card");
    expect(call[6]).toEqual({
      preferCheckout: true,
      preferredTariffKey: "pro",
      selectDefaultTariff: true,
    });
    expect(deps.stripRenewalLoginQueryFromUrl).toHaveBeenCalledOnce();
  });

  it("applies both topup and renewal deeplinks when both resolve", () => {
    const { deps, effects } = makeEffects({
      readRenewalDeeplink: vi.fn(() => ({ tariffKey: "pro" })),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "?topup=regular&after_login=renew",
      subscription: activeRegularSubscription,
    });

    expect(deps.billingStore.openTopupModal).toHaveBeenCalledOnce();
    expect(deps.stripTopupQueryFromUrl).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
    expect(deps.setHomeRoute).toHaveBeenCalledOnce();
    expect(deps.stripRenewalLoginQueryFromUrl).toHaveBeenCalledOnce();
  });

  it("opens plan selection on the checkout route", () => {
    const { deps, effects } = makeEffects({ readPlansDeeplink: vi.fn(() => true) });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "",
      subscription: { active: false },
    });

    // The route has no screen of its own, so it lands on home with plan and
    // period selection already open.
    expect(deps.setHomeRoute).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
    const call = deps.billingStore.openPaymentModal.mock.calls[0];
    expect(call[0]).toBe(true);
    expect(call[6]).toEqual({
      preferCheckout: true,
      preferredTariffKey: "",
      selectDefaultTariff: true,
    });
  });

  it("opens an exact plan checkout with URL-selected flexible limits", () => {
    const checkoutDeeplink = {
      plan: "pro",
      months: 6,
      addons: { deviceTotal: 5, regularLimitGb: 300, premiumLimitGb: 100 },
    };
    const { deps, effects } = makeEffects({
      readCheckoutDeeplink: vi.fn(() => checkoutDeeplink),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: [{ id: 8, tariff_key: "pro", months: 6 }],
      search: "",
      subscription: { active: false },
    });

    expect(deps.setHomeRoute).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal.mock.calls[0][6]).toEqual({
      preferCheckout: true,
      preferredPlanId: "pro",
      preferredTariffKey: "pro",
      preferredMonths: 6,
      checkoutAddonPreset: checkoutDeeplink.addons,
    });
    expect(deps.stripCheckoutDeeplinkFromUrl).toHaveBeenCalledOnce();
  });

  it("consumes checkout entry once when later data refreshes rerun post-load effects", () => {
    const checkoutDeeplink = { plan: "pro", months: 6, addons: {} };
    const { deps, effects } = makeEffects({
      readCheckoutDeeplink: vi.fn(() => checkoutDeeplink),
      readPlansDeeplink: vi.fn(() => true),
    });
    const input = {
      defaultMethod: "card",
      plans: [{ id: 8, tariff_key: "pro", months: 6 }],
      search: "",
      subscription: { active: false },
    };

    effects.applyPostLoadBillingDeeplinks(input);
    effects.applyPostLoadBillingDeeplinks(input);

    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
    expect(deps.stripCheckoutDeeplinkFromUrl).toHaveBeenCalledOnce();
  });

  it("does not reopen plan selection from a persistent checkout route flag", () => {
    const { deps, effects } = makeEffects({ readPlansDeeplink: vi.fn(() => true) });
    const input = {
      defaultMethod: "card",
      plans: tariffPlans,
      search: "",
      subscription: { active: false },
    };

    effects.applyPostLoadBillingDeeplinks(input);
    effects.applyPostLoadBillingDeeplinks(input);

    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
  });

  it("lets a more specific billing deeplink win over the checkout route", () => {
    const { deps, effects } = makeEffects({
      readPlansDeeplink: vi.fn(() => true),
      readRenewalDeeplink: vi.fn(() => ({ tariffKey: "pro" })),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "?topup=regular",
      subscription: activeRegularSubscription,
    });

    // Topup and renewal both name what to buy; the plain checkout route does
    // not, so it must never replace one of them.
    expect(deps.billingStore.openTopupModal).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal.mock.calls[0][6].preferredTariffKey).toBe("pro");
  });

  it("delegates a code deeplink to the status-aware handler when provided", () => {
    const handleCheckoutPromoDeeplink = vi.fn();
    const { deps, effects } = makeEffects({
      handleCheckoutPromoDeeplink,
      readCheckoutPromoDeeplink: vi.fn(() => "SAVE10"),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: [{ tariff_key: "pro", is_default_tariff: true }],
      search: "?startapp=promo_SAVE10",
      subscription: { active: false },
    });

    expect(handleCheckoutPromoDeeplink).toHaveBeenCalledWith("SAVE10", { modalOpened: false });
    expect(deps.stripCheckoutPromoQueryFromUrl).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).not.toHaveBeenCalled();
    expect(deps.billingStore.applyCheckoutPromo).not.toHaveBeenCalled();
  });

  it("passes a real Telegram startapp promo code to the checkout handler", () => {
    vi.stubGlobal("window", { location: { search: "?startapp=promo_SAVE20" } });
    const handleCheckoutPromoDeeplink = vi.fn();
    const { effects } = makeEffects({
      handleCheckoutPromoDeeplink,
      readCheckoutPromoDeeplink,
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: [{ tariff_key: "pro", is_default_tariff: true }],
      search: "?startapp=promo_SAVE20",
      subscription: { active: false },
    });

    expect(handleCheckoutPromoDeeplink).toHaveBeenCalledWith("SAVE20", {
      modalOpened: false,
    });
  });

  it("reports an already opened deeplink modal to the promo handler", () => {
    const handleCheckoutPromoDeeplink = vi.fn();
    const { effects } = makeEffects({
      handleCheckoutPromoDeeplink,
      readCheckoutPromoDeeplink: vi.fn(() => "SAVE10"),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: tariffPlans,
      search: "?topup=regular&startapp=promo_SAVE10",
      subscription: activeRegularSubscription,
    });

    expect(handleCheckoutPromoDeeplink).toHaveBeenCalledWith("SAVE10", { modalOpened: true });
  });

  it("prefills checkout code and opens default checkout from a code deeplink", () => {
    const { deps, effects } = makeEffects({
      readCheckoutPromoDeeplink: vi.fn(() => "SAVE10"),
    });

    effects.applyPostLoadBillingDeeplinks({
      defaultMethod: "card",
      plans: [{ tariff_key: "pro", is_default_tariff: true }],
      search: "?startapp=promo_SAVE10",
      subscription: { active: false },
    });

    expect(deps.billingStore.setCheckoutPromoInput).toHaveBeenCalledWith("SAVE10");
    expect(deps.setHomeRoute).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal).toHaveBeenCalledOnce();
    expect(deps.billingStore.openPaymentModal.mock.calls[0][6]).toEqual({
      preferCheckout: true,
      preferredTariffKey: "",
      selectDefaultTariff: true,
    });
    expect(deps.billingStore.applyCheckoutPromo).toHaveBeenCalledOnce();
    expect(deps.stripCheckoutPromoQueryFromUrl).toHaveBeenCalledOnce();
  });
});
