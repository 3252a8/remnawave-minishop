import {
  renewalPaymentConfig,
  resolveTopupDeeplinkKind,
  type RenewalPaymentConfig,
} from "./billingDeeplinks.js";
import { buildTariffCatalog } from "./tariffs.js";
import type { BillingPlan } from "./tariffs.js";
import type { SubscriptionView } from "./types";
import type { CheckoutDeeplink } from "./deeplinks.js";

type BillingDeeplinkPaymentOptions = {
  checkoutAddonPreset?: CheckoutDeeplink["addons"];
  preferCheckout?: boolean;
  preferredMonths?: number | null;
  preferredPlanId?: string;
  preferredTariffKey?: string;
  selectDefaultTariff?: boolean;
};

type BillingDeeplinkStore = {
  applyCheckoutPromo?: () => Promise<void>;
  openPaymentModal: (
    tariffMode: boolean,
    singleTariffMode: boolean,
    tariffCatalog: RenewalPaymentConfig["tariffCatalog"],
    subscription: SubscriptionView,
    plans: BillingPlan[],
    defaultMethod: string,
    options: BillingDeeplinkPaymentOptions
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
  readCheckoutDeeplink?: () => CheckoutDeeplink | null;
  /** True when the app was opened on the checkout route. */
  readPlansDeeplink?: () => boolean;
  readRenewalDeeplink: () => { tariffKey: string } | null;
  setHomeRoute: () => void;
  showTariffAccessError?: () => void;
  stripCheckoutPromoQueryFromUrl?: () => void;
  stripCheckoutDeeplinkFromUrl?: () => void;
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
  readCheckoutDeeplink = () => null,
  readPlansDeeplink = () => false,
  readRenewalDeeplink,
  setHomeRoute,
  showTariffAccessError = () => {},
  stripCheckoutPromoQueryFromUrl = () => {},
  stripCheckoutDeeplinkFromUrl = () => {},
  stripRenewalLoginQueryFromUrl,
  stripTopupQueryFromUrl,
}: BillingDeeplinkEffectsDeps) {
  // Checkout routing is an entry intent, not persistent UI state. loadData()
  // runs again for quotes, resume refreshes, and other background updates; if
  // the route were read on every pass it could reopen plan selection over an
  // in-progress checkout.
  let checkoutEntryConsumed = false;

  function applyPostLoadBillingDeeplinks({
    defaultMethod,
    plans,
    search,
    subscription,
  }: ApplyPostLoadBillingDeeplinksInput): void {
    let openedBillingDeeplink = false;
    const checkoutDeeplink = checkoutEntryConsumed ? null : readCheckoutDeeplink();
    const plansDeeplinkRequested = !checkoutEntryConsumed && readPlansDeeplink();
    if (checkoutDeeplink || plansDeeplinkRequested) checkoutEntryConsumed = true;

    const topupDeeplinkKind = resolveTopupDeeplinkKind({ plans, search, subscription });
    if (topupDeeplinkKind) {
      billingStore.openTopupModal(topupDeeplinkKind, defaultMethod);
      stripTopupQueryFromUrl();
      openedBillingDeeplink = true;
    }

    if (!openedBillingDeeplink && checkoutDeeplink) {
      const accessPlan = checkoutDeeplink.accessCode
        ? plans.find((plan) => plan.access_via_link === true)
        : null;
      setHomeRoute();
      if (checkoutDeeplink.accessCode && !accessPlan) {
        stripCheckoutDeeplinkFromUrl();
        showTariffAccessError();
        return;
      }
      const requestedPlan = String(accessPlan?.tariff_key || checkoutDeeplink.plan || "");
      billingStore.openPaymentModal(
        plans.some((plan) => plan?.tariff_key),
        false,
        buildTariffCatalog(plans),
        subscription,
        plans,
        defaultMethod,
        {
          preferCheckout: true,
          preferredPlanId: requestedPlan,
          preferredTariffKey: requestedPlan,
          preferredMonths: checkoutDeeplink.months,
          checkoutAddonPreset: checkoutDeeplink.addons,
          ...(requestedPlan ? {} : { selectDefaultTariff: true }),
        }
      );
      stripCheckoutDeeplinkFromUrl();
      openedBillingDeeplink = true;
    }

    if (!openedBillingDeeplink && plansDeeplinkRequested) {
      // The checkout route has no screen of its own: it lands on home and
      // opens plan selection, so the customer picks a plan and a period in
      // one step instead of hunting for the button.
      setHomeRoute();
      billingStore.openPaymentModal(
        plans.some((plan) => plan?.tariff_key),
        false,
        buildTariffCatalog(plans),
        subscription,
        plans,
        defaultMethod,
        { preferCheckout: true, preferredTariffKey: "", selectDefaultTariff: true }
      );
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
