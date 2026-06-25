import type { BillingPlan, TariffCatalogEntry } from "./tariffs.js";

type WebappRecord = Record<string, unknown>;

type TariffActionsBillingStore = {
  backToTariffList: (subscription: WebappRecord, tariffCatalog: TariffCatalogEntry[]) => void;
  continueWithSelectedTariff: (selectedTariffPlans: BillingPlan[]) => void;
  selectTariff: (tariff: TariffCatalogEntry, plans: BillingPlan[]) => void;
};

type TariffActionDeps = {
  billingStore: TariffActionsBillingStore;
  getPlans: () => BillingPlan[];
  getSelectedTariffPlans: () => BillingPlan[];
  getSubscription: () => WebappRecord;
  getTariffCatalog: () => TariffCatalogEntry[];
};

export function createTariffActions({
  billingStore,
  getPlans,
  getSelectedTariffPlans,
  getSubscription,
  getTariffCatalog,
}: TariffActionDeps) {
  function selectTariff(tariff: TariffCatalogEntry) {
    billingStore.selectTariff(tariff, getPlans());
  }

  function continueWithSelectedTariff() {
    billingStore.continueWithSelectedTariff(getSelectedTariffPlans());
  }

  function backToTariffList() {
    billingStore.backToTariffList(getSubscription(), getTariffCatalog());
  }

  return {
    backToTariffList,
    continueWithSelectedTariff,
    selectTariff,
  };
}
