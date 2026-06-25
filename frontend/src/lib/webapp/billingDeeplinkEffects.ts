import {
  renewalPaymentConfig,
  resolveTopupDeeplinkKind,
  type RenewalPaymentConfig,
} from "./billingDeeplinks.js";
import type { BillingPlan } from "./tariffs.js";

type WebappRecord = Record<string, unknown>;

type BillingDeeplinkStore = {
  openPaymentModal: (
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: RenewalPaymentConfig["tariffCatalog"],
    subscription: WebappRecord,
    plans: BillingPlan[],
    defaultMethod: string,
    options: RenewalPaymentConfig["options"]
  ) => void;
  openTopupModal: (kind: "premium" | "regular", defaultMethod: string) => void;
};

export type BillingDeeplinkEffectsDeps = {
  billingStore: BillingDeeplinkStore;
  readRenewalDeeplink: () => { tariffKey: string } | null;
  setHomeRoute: () => void;
  stripRenewalLoginQueryFromUrl: () => void;
  stripTopupQueryFromUrl: () => void;
};

export type ApplyPostLoadBillingDeeplinksInput = {
  defaultMethod: string;
  plans: BillingPlan[];
  search: string;
  subscription: WebappRecord;
};

export function createBillingDeeplinkEffects({
  billingStore,
  readRenewalDeeplink,
  setHomeRoute,
  stripRenewalLoginQueryFromUrl,
  stripTopupQueryFromUrl,
}: BillingDeeplinkEffectsDeps) {
  function applyPostLoadBillingDeeplinks({
    defaultMethod,
    plans,
    search,
    subscription,
  }: ApplyPostLoadBillingDeeplinksInput): void {
    const topupDeeplinkKind = resolveTopupDeeplinkKind({ plans, search, subscription });
    if (topupDeeplinkKind) {
      billingStore.openTopupModal(topupDeeplinkKind, defaultMethod);
      stripTopupQueryFromUrl();
    }

    const renewalDeep = readRenewalDeeplink();
    if (renewalDeep) {
      const renewalPayment = renewalPaymentConfig({
        defaultMethod,
        plans,
        subscription,
        tariffKey: renewalDeep.tariffKey,
      });
      setHomeRoute();
      billingStore.openPaymentModal(
        renewalPayment.tariffMode,
        renewalPayment.singleTariffMode,
        renewalPayment.tariffCatalog,
        renewalPayment.subscription,
        renewalPayment.plans,
        renewalPayment.defaultMethod,
        renewalPayment.options
      );
      stripRenewalLoginQueryFromUrl();
    }
  }

  return { applyPostLoadBillingDeeplinks };
}
