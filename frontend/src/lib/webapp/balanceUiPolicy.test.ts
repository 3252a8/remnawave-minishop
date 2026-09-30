import { describe, expect, it } from "vitest";

import {
  availableBalanceTopupMethods,
  shouldShowUserBalance,
  decimalTopupAmount,
} from "./balanceUiPolicy.js";

describe("user balance UI policy", () => {
  it("accepts ordinary decimal amounts at currency precision", () => {
    expect(decimalTopupAmount("100,12", 2)).toBe(100.12);
    expect(decimalTopupAmount("100.125", 3)).toBe(100.125);
    for (const value of ["1e2", "abc", "Infinity", "100.125", "1.", "0", "-1"])
      expect(decimalTopupAmount(value, 2)).toBeNull();
    expect(decimalTopupAmount("100.1", 0)).toBeNull();
  });
  it("shows a positive balance even when top-ups are disabled", () => {
    expect(shouldShowUserBalance({ enabled: false, amount_minor: 1_000 })).toBe(true);
  });

  it("hides an empty disabled balance", () => {
    expect(shouldShowUserBalance({ enabled: false, amount_minor: 0 })).toBe(false);
  });

  it("keeps an enabled empty balance visible for top-ups", () => {
    expect(shouldShowUserBalance({ enabled: true, amount_minor: 0 })).toBe(true);
  });

  it("keeps one-off methods and hides recurring and internal methods from top-ups", () => {
    const methods = [
      { id: "rollypay" },
      { id: "rollypay_subscription" },
      { id: "platega_subscription" },
      { id: "wata_subscription" },
      { id: "tribute" },
      { id: "stars" },
      { id: "partner_balance" },
      { id: "user_balance" },
      { id: "external", price_managed_externally: true },
    ];

    expect(availableBalanceTopupMethods(methods)).toEqual([{ id: "rollypay" }]);
  });
});
