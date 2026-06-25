type PromoTrialStore = {
  activateTrial: () => unknown;
  applyPromo: () => unknown;
  clearPromoFieldError: () => void;
  setPromoCode: (value: string) => void;
};

type PromoTrialActionDeps = {
  actionsStore: PromoTrialStore;
};

export function createPromoTrialActions({ actionsStore }: PromoTrialActionDeps) {
  function applyPromo() {
    return actionsStore.applyPromo();
  }

  function setPromoCode(value: string) {
    actionsStore.setPromoCode(value);
  }

  function clearPromoFieldError() {
    actionsStore.clearPromoFieldError();
  }

  function activateTrial() {
    return actionsStore.activateTrial();
  }

  return {
    activateTrial,
    applyPromo,
    clearPromoFieldError,
    setPromoCode,
  };
}
