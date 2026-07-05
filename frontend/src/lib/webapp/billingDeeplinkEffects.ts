import {
  renewalPaymentConfig,
  resolveTopupDeeplinkKind,
  type RenewalPaymentConfig,
} from "./billingDeeplinks.js";
import { buildTariffCatalog } from "./tariffs.js";
import type { BillingPlan } from "./tariffs.js";
import type { SubscriptionView } from "./types";

type BillingDeeplinkStore = {
  applyCheckoutPromo?: () => Promise<void>;
  openPaymentModal: (
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: RenewalPaymentConfig["tariffCatalog"],
    subscription: SubscriptionView,
    plans: BillingPlan[],
    defaultMethod: string,
    options: RenewalPaymentConfig["options"]
  ) => void;
  openTopupModal: (kind: "premium" | "regular", defaultMethod: string) => void;
  setCheckoutPromoInput?: (value: string) => void;
};

export type BillingDeeplinkEffectsDeps = {
  billingStore: BillingDeeplinkStore;
  /**
   * Status-aware promo deeplink handler. When provided it decides whether to
   * open checkout or show an explanatory dialog (already used / invalid code)
   * instead of always opening checkout with an erroring promo field.
   */
  handleCheckoutPromoDeeplink?: (code: string, context: { modalOpened: boolean }) => void;
  readCheckoutPromoDeeplink?: () => string;
  readRenewalDeeplink: () => { tariffKey: string } | null;
  setHomeRoute: () => void;
  stripCheckoutPromoQueryFromUrl?: () => void;
  stripRenewalLoginQueryFromUrl: () => void;
  stripTopupQueryFromUrl: () => void;
};

export type ApplyPostLoadBillingDeeplinksInput = {
  defaultMethod: string;
  plans: BillingPlan[];
  search: string;
  subscription: SubscriptionView;
};

export function createBillingDeeplinkEffects({
  billingStore,
  handleCheckoutPromoDeeplink,
  readCheckoutPromoDeeplink = () => "",
  readRenewalDeeplink,
  setHomeRoute,
  stripCheckoutPromoQueryFromUrl = () => {},
  stripRenewalLoginQueryFromUrl,
  stripTopupQueryFromUrl,
}: BillingDeeplinkEffectsDeps) {
  function applyPostLoadBillingDeeplinks({
    defaultMethod,
    plans,
    search,
    subscription,
  }: ApplyPostLoadBillingDeeplinksInput): void {
    let openedBillingDeeplink = false;
    const topupDeeplinkKind = resolveTopupDeeplinkKind({ plans, search, subscription });
    if (topupDeeplinkKind) {
      billingStore.openTopupModal(topupDeeplinkKind, defaultMethod);
      stripTopupQueryFromUrl();
      openedBillingDeeplink = true;
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
      openedBillingDeeplink = true;
    }

    const checkoutPromoCode = readCheckoutPromoDeeplink();
    if (checkoutPromoCode) {
      stripCheckoutPromoQueryFromUrl();
      if (handleCheckoutPromoDeeplink) {
        handleCheckoutPromoDeeplink(checkoutPromoCode, { modalOpened: openedBillingDeeplink });
        return;
      }
      billingStore.setCheckoutPromoInput?.(checkoutPromoCode);
      if (!openedBillingDeeplink) {
        setHomeRoute();
        billingStore.openPaymentModal(
          true,
          true,
          buildTariffCatalog(plans),
          subscription,
          plans,
          defaultMethod,
          {
            preferCheckout: true,
            preferredTariffKey: "",
            selectDefaultTariff: true,
          }
        );
      }
      void billingStore.applyCheckoutPromo?.();
    }
  }

  return { applyPostLoadBillingDeeplinks };
}
