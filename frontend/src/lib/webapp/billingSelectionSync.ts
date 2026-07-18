import type { BillingPlan, PaymentMethod, TariffCatalogEntry } from "./tariffs.js";

export type BillingSelectionState = {
  paymentStep: string;
  selectedMethod: string;
  selectedPlan: BillingPlan | null;
  selectedTariffKey: string;
};

export type BillingSelectionInput = {
  methods: PaymentMethod[];
  plans: BillingPlan[];
  selectedTariffPlans: BillingPlan[];
  singleTariffMode: boolean;
  tariffCatalog: TariffCatalogEntry[];
  tariffMode: boolean;
};

export function reconcileBillingSelection(
  state: BillingSelectionState,
  input: BillingSelectionInput
): Partial<BillingSelectionState> | null {
  const draft: BillingSelectionState = { ...state };
  const patch: Partial<BillingSelectionState> = {};

  function set<K extends keyof BillingSelectionState>(key: K, value: BillingSelectionState[K]) {
    if (draft[key] === value) return;
    draft[key] = value;
    patch[key] = value;
  }

  if (!input.tariffMode && !draft.selectedPlan && input.plans.length) {
    set("selectedPlan", input.plans[Math.min(1, input.plans.length - 1)]);
  }

  if (
    input.singleTariffMode &&
    input.tariffCatalog[0]?.key &&
    draft.selectedTariffKey !== input.tariffCatalog[0].key
  ) {
    const tariffKey = input.tariffCatalog[0].key;
    set("selectedTariffKey", tariffKey);
    set("selectedPlan", input.plans.find((plan) => plan?.tariff_key === tariffKey) || null);
    set("paymentStep", draft.paymentStep === "tariff" ? "checkout" : draft.paymentStep);
  }

  if (
    input.tariffMode &&
    draft.selectedTariffKey &&
    !input.tariffCatalog.some((tariff) => tariff.key === draft.selectedTariffKey)
  ) {
    set("selectedTariffKey", "");
    set("selectedPlan", null);
    set("paymentStep", input.singleTariffMode ? "checkout" : "tariff");
  }

  if (
    input.tariffMode &&
    draft.selectedTariffKey &&
    (!draft.selectedPlan || draft.selectedPlan.tariff_key !== draft.selectedTariffKey)
  ) {
    set("selectedPlan", input.selectedTariffPlans[0] || null);
  }

  if (input.methods.length) {
    const selectedMethodAvailable = input.methods.some(
      (method) => method.id === draft.selectedMethod && !method.disabled
    );
    if (!draft.selectedMethod || !selectedMethodAvailable) {
      set("selectedMethod", String(input.methods.find((method) => !method.disabled)?.id || ""));
    }
  } else if (draft.selectedMethod) {
    set("selectedMethod", "");
  }

  return Object.keys(patch).length ? patch : null;
}
