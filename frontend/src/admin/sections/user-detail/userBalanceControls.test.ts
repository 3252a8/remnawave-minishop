import { describe, expect, it } from "vitest";

import {
  balanceAdjustmentValid,
  defaultBalanceTarget,
  resolveBalanceTarget,
} from "./userBalanceControls.js";

describe("user balance controls", () => {
  it("selects the partner balance when the main balance is disabled", () => {
    expect(defaultBalanceTarget(false, true)).toBe("partner");
    expect(defaultBalanceTarget(true, true)).toBe("user");
  });

  it("keeps the selected balance while it remains available", () => {
    expect(resolveBalanceTarget("partner", true, true)).toBe("partner");
    expect(resolveBalanceTarget("user", true, true)).toBe("user");
  });

  it("reports that no balance can be managed when both targets are unavailable", () => {
    expect(resolveBalanceTarget("user", false, false)).toBeNull();
  });

  it("rejects no-op and overdraft adjustments but permits setting zero", () => {
    const base = { amountFactor: 100, currentAmountMinor: 1_000, targetAvailable: true };
    expect(balanceAdjustmentValid({ ...base, mode: "add", value: "0" })).toBe(false);
    expect(balanceAdjustmentValid({ ...base, mode: "subtract", value: "10.01" })).toBe(false);
    expect(balanceAdjustmentValid({ ...base, mode: "subtract", value: "10" })).toBe(true);
    expect(balanceAdjustmentValid({ ...base, mode: "set", value: "0" })).toBe(true);
  });
});
