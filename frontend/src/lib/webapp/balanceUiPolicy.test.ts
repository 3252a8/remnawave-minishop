import { describe, expect, it } from "vitest";

import { shouldShowUserBalance } from "./balanceUiPolicy.js";

describe("user balance UI policy", () => {
  it("shows a positive balance even when top-ups are disabled", () => {
    expect(shouldShowUserBalance({ enabled: false, amount_minor: 1_000 })).toBe(true);
  });

  it("hides an empty disabled balance", () => {
    expect(shouldShowUserBalance({ enabled: false, amount_minor: 0 })).toBe(false);
  });

  it("keeps an enabled empty balance visible for top-ups", () => {
    expect(shouldShowUserBalance({ enabled: true, amount_minor: 0 })).toBe(true);
  });
});
