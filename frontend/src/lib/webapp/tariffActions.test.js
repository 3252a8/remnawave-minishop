import { describe, expect, it, vi } from "vitest";

import { createTariffActions } from "./tariffActions.js";

function makeActions() {
  const state = {
    plans: [{ id: "plan", tariff_key: "pro" }],
    selectedTariffPlans: [{ id: "selected", tariff_key: "pro" }],
    subscription: { active: false },
    tariff: { billing_model: "period", key: "pro", title: "Pro" },
    tariffCatalog: [{ billing_model: "period", key: "pro", title: "Pro" }],
  };
  const billingStore = {
    backToTariffList: vi.fn(),
    continueWithSelectedTariff: vi.fn(),
    selectTariff: vi.fn(),
  };
  const actions = createTariffActions({
    billingStore,
    getPlans: () => state.plans,
    getSelectedTariffPlans: () => state.selectedTariffPlans,
    getSubscription: () => state.subscription,
    getTariffCatalog: () => state.tariffCatalog,
  });
  return { actions, billingStore, state };
}

describe("createTariffActions", () => {
  it("selects tariffs with the current plan list", () => {
    const { actions, billingStore, state } = makeActions();

    actions.selectTariff(state.tariff);

    expect(billingStore.selectTariff).toHaveBeenCalledWith(state.tariff, state.plans);
  });

  it("continues and returns to tariff selection with current billing state", () => {
    const { actions, billingStore, state } = makeActions();

    actions.continueWithSelectedTariff();
    actions.backToTariffList();

    expect(billingStore.continueWithSelectedTariff).toHaveBeenCalledWith(state.selectedTariffPlans);
    expect(billingStore.backToTariffList).toHaveBeenCalledWith(
      state.subscription,
      state.tariffCatalog
    );
  });
});
