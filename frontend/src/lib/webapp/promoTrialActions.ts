import type { AppSettings, PlanView } from "./types.js";

type PromoTrialStore = {
  activateTrial: () => unknown;
  applyPromo: () => unknown;
  clearPromoFieldError: () => void;
  openPromoCheckout: () => void;
  setPromoCode: (value: string) => void;
};

type PromoTrialActionDeps = {
  actionsStore: PromoTrialStore;
  getAppSettings: () => AppSettings | null | undefined;
  openTrialPayment: (plan: PlanView) => unknown;
};

export function createPromoTrialActions({
  actionsStore,
  getAppSettings,
  openTrialPayment,
}: PromoTrialActionDeps) {
  function applyPromo() {
    return actionsStore.applyPromo();
  }

  function setPromoCode(value: string) {
    actionsStore.setPromoCode(value);
  }

  function clearPromoFieldError() {
    actionsStore.clearPromoFieldError();
  }

  function openPromoCheckout() {
    actionsStore.openPromoCheckout();
  }

  function activateTrial() {
    const settings = getAppSettings();
    const paymentPlan = settings?.trial_payment_plan as PlanView | null | undefined;
    if (settings?.trial_payment_enabled && paymentPlan) {
      return openTrialPayment(paymentPlan);
    }
    return actionsStore.activateTrial();
  }

  return {
    activateTrial,
    applyPromo,
    clearPromoFieldError,
    openPromoCheckout,
    setPromoCode,
  };
}
