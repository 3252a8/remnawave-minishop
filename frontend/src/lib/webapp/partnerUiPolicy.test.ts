import { describe, expect, it } from "vitest";

import {
  partnerBalanceLookupKey,
  partnerLoadingPlaceholder,
  shouldShowPartnerBalanceDiscount,
  shouldShowPartnerBalancePlaceholder,
} from "./partnerUiPolicy.js";

describe("partner UI policy", () => {
  it("keeps the balance lookup stable while checkout pricing changes", () => {
    expect(partnerBalanceLookupKey({ open: true, eligible: true, currency: "rub" })).toBe("RUB");
    expect(partnerBalanceLookupKey({ open: true, eligible: true, currency: "RUB" })).toBe("RUB");
  });

  it("does not load a balance for unavailable checkout states", () => {
    expect(partnerBalanceLookupKey({ open: false, eligible: true, currency: "RUB" })).toBe("");
    expect(partnerBalanceLookupKey({ open: true, eligible: false, currency: "RUB" })).toBe("");
    expect(partnerBalanceLookupKey({ open: true, eligible: true, currency: "" })).toBe("");
  });

  it("keeps the balance option hidden until a positive discount is confirmed", () => {
    const checkout = {
      open: true,
      eligible: true,
      currency: "RUB",
      maximumDiscount: 0,
    };

    expect(shouldShowPartnerBalanceDiscount(checkout)).toBe(false);
    expect(shouldShowPartnerBalanceDiscount({ ...checkout, maximumDiscount: 120 })).toBe(true);
  });

  it("keeps unavailable checkout states hidden", () => {
    expect(
      shouldShowPartnerBalanceDiscount({
        open: true,
        eligible: false,
        currency: "RUB",
        maximumDiscount: 120,
      })
    ).toBe(false);
    expect(
      shouldShowPartnerBalanceDiscount({
        open: false,
        eligible: true,
        currency: "RUB",
        maximumDiscount: 120,
      })
    ).toBe(false);
  });

  it("reserves the balance option before and during its first lookup", () => {
    const checkout = {
      open: true,
      eligible: true,
      currency: "RUB",
      loading: false,
      requestKey: "",
    };

    expect(shouldShowPartnerBalancePlaceholder(checkout)).toBe(true);
    expect(
      shouldShowPartnerBalancePlaceholder({ ...checkout, loading: true, requestKey: "RUB" })
    ).toBe(true);
    expect(
      shouldShowPartnerBalancePlaceholder({ ...checkout, loading: false, requestKey: "RUB" })
    ).toBe(false);
  });

  it("does not reserve a balance option for ineligible checkout states", () => {
    expect(
      shouldShowPartnerBalancePlaceholder({
        open: false,
        eligible: true,
        currency: "RUB",
        loading: true,
        requestKey: "RUB",
      })
    ).toBe(false);
    expect(
      shouldShowPartnerBalancePlaceholder({
        open: true,
        eligible: false,
        currency: "RUB",
        loading: true,
        requestKey: "RUB",
      })
    ).toBe(false);
  });

  it("uses the partner dashboard skeleton only in explicit preview mode", () => {
    expect(partnerLoadingPlaceholder(false)).toBe("neutral");
    expect(partnerLoadingPlaceholder(true)).toBe("dashboard");
  });
});
