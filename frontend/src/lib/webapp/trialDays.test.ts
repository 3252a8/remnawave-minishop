import { describe, expect, it } from "vitest";

import { isActiveTrialSubscription } from "./trialDays.js";

describe("active trial checkout", () => {
  it("recognizes active trials by provider or status", () => {
    expect(isActiveTrialSubscription({ active: true, provider: "trial" })).toBe(true);
    expect(isActiveTrialSubscription({ active: true, status: "TRIAL" })).toBe(true);
  });

  it("does not expose the strategy for inactive or paid subscriptions", () => {
    expect(isActiveTrialSubscription({ active: false, provider: "trial" })).toBe(false);
    expect(isActiveTrialSubscription({ active: true, provider: "yookassa" })).toBe(false);
  });
});
