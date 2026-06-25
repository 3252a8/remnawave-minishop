import { describe, expect, it } from "vitest";

import { reconcileBillingSelection } from "./billingSelectionSync.js";

const BASE_STATE = {
  paymentStep: "tariff",
  selectedMethod: "",
  selectedPlan: null,
  selectedTariffKey: "",
};

const BASE_INPUT = {
  methods: [],
  plans: [],
  selectedTariffPlans: [],
  singleTariffMode: false,
  tariffCatalog: [],
  tariffMode: false,
};

describe("reconcileBillingSelection", () => {
  it("selects the second legacy plan when no plan is selected", () => {
    const plans = [{ id: "monthly" }, { id: "yearly" }];

    expect(reconcileBillingSelection(BASE_STATE, { ...BASE_INPUT, plans })).toEqual({
      selectedPlan: plans[1],
    });
  });

  it("pins single-tariff mode to the only tariff and skips the tariff step", () => {
    const plans = [{ id: "basic", tariff_key: "basic" }];

    expect(
      reconcileBillingSelection(
        { ...BASE_STATE, selectedTariffKey: "old" },
        {
          ...BASE_INPUT,
          plans,
          singleTariffMode: true,
          tariffCatalog: [{ key: "basic" }],
          tariffMode: true,
        }
      )
    ).toEqual({
      paymentStep: "checkout",
      selectedPlan: plans[0],
      selectedTariffKey: "basic",
    });
  });

  it("clears a selected tariff key that is no longer present", () => {
    expect(
      reconcileBillingSelection(
        { ...BASE_STATE, selectedPlan: { id: "stale" }, selectedTariffKey: "stale" },
        { ...BASE_INPUT, tariffCatalog: [{ key: "active" }], tariffMode: true }
      )
    ).toEqual({
      selectedPlan: null,
      selectedTariffKey: "",
    });
  });

  it("selects the first plan for the active tariff", () => {
    const selectedTariffPlans = [{ id: "pro-month", tariff_key: "pro" }];

    expect(
      reconcileBillingSelection(
        { ...BASE_STATE, selectedTariffKey: "pro" },
        {
          ...BASE_INPUT,
          selectedTariffPlans,
          tariffCatalog: [{ key: "pro" }],
          tariffMode: true,
        }
      )
    ).toEqual({
      selectedPlan: selectedTariffPlans[0],
    });
  });

  it("defaults and clears payment methods", () => {
    expect(
      reconcileBillingSelection(BASE_STATE, {
        ...BASE_INPUT,
        methods: [{ id: "card" }, { id: "crypto" }],
      })
    ).toEqual({ selectedMethod: "card" });

    expect(
      reconcileBillingSelection({ ...BASE_STATE, selectedMethod: "card" }, BASE_INPUT)
    ).toEqual({ selectedMethod: "" });
  });

  it("returns null when the current selection is still valid", () => {
    const selectedPlan = { id: "pro-month", tariff_key: "pro" };

    expect(
      reconcileBillingSelection(
        {
          paymentStep: "checkout",
          selectedMethod: "card",
          selectedPlan,
          selectedTariffKey: "pro",
        },
        {
          ...BASE_INPUT,
          methods: [{ id: "card" }],
          selectedTariffPlans: [selectedPlan],
          tariffCatalog: [{ key: "pro" }],
          tariffMode: true,
        }
      )
    ).toBeNull();
  });
});
