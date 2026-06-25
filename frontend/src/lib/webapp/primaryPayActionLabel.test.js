import { describe, expect, it, vi } from "vitest";

import {
  createPrimaryPayActionLabel,
  resolvePrimaryPayActionLabel,
} from "./primaryPayActionLabel.js";

const payFullSubscriptionFallback =
  "\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c \u043f\u043e\u043b\u043d\u0443\u044e \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443";
const renewSubscriptionFallback =
  "\u041f\u0440\u043e\u0434\u043b\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443";

function makeT() {
  return vi.fn((key) => key);
}

describe("resolvePrimaryPayActionLabel", () => {
  it("uses the full-subscription label when trial is still available", () => {
    const t = makeT();

    expect(
      resolvePrimaryPayActionLabel({
        appSettings: { trial_available: true, trial_enabled: true },
        selectedPlan: null,
        subscription: { active: false },
        t,
        trafficMode: false,
      })
    ).toBe("wa_pay_full_subscription");

    expect(t).toHaveBeenCalledWith("wa_pay_full_subscription", {}, payFullSubscriptionFallback);
  });

  it("uses the traffic label for traffic mode or traffic package plans", () => {
    const t = makeT();

    expect(
      resolvePrimaryPayActionLabel({
        appSettings: {},
        selectedPlan: null,
        subscription: { active: false },
        t,
        trafficMode: true,
      })
    ).toBe("wa_buy_traffic");
    expect(
      resolvePrimaryPayActionLabel({
        appSettings: {},
        selectedPlan: { sale_mode: "traffic_package" },
        subscription: { active: false },
        t,
        trafficMode: false,
      })
    ).toBe("wa_buy_traffic");
  });

  it("uses renewal or payment labels for regular subscriptions", () => {
    const t = makeT();

    expect(
      resolvePrimaryPayActionLabel({
        appSettings: {},
        selectedPlan: null,
        subscription: { active: true },
        t,
        trafficMode: false,
      })
    ).toBe("wa_renew_subscription");
    expect(t).toHaveBeenCalledWith("wa_renew_subscription", {}, renewSubscriptionFallback);

    expect(
      resolvePrimaryPayActionLabel({
        appSettings: {},
        selectedPlan: null,
        subscription: { active: false },
        t,
        trafficMode: false,
      })
    ).toBe("wa_pay_subscription");
  });
});

describe("createPrimaryPayActionLabel", () => {
  it("reads the latest state through getters", () => {
    const state = {
      appSettings: {},
      selectedPlan: null,
      subscription: { active: false },
      trafficMode: false,
    };
    const primaryPayActionLabel = createPrimaryPayActionLabel({
      getAppSettings: () => state.appSettings,
      getSelectedPlan: () => state.selectedPlan,
      getSubscription: () => state.subscription,
      getTrafficMode: () => state.trafficMode,
      t: makeT(),
    });

    expect(primaryPayActionLabel()).toBe("wa_pay_subscription");

    state.subscription = { active: true };

    expect(primaryPayActionLabel()).toBe("wa_renew_subscription");
  });
});
