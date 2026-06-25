import { describe, expect, it, vi } from "vitest";

import { createBillingDeeplinkEffects } from "./billingDeeplinkEffects.js";

function makeEffects(overrides = {}) {
  const deps = {
    billingStore: {
      openPaymentModal: vi.fn(),
      openTopupModal: vi.fn(),
    },
    readRenewalDeeplink: vi.fn(() => null),
    setHomeRoute: vi.fn(),
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
});
