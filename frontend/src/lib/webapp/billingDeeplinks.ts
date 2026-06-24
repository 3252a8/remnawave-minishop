import { buildTariffCatalog, type BillingPlan, type TariffCatalogEntry } from "./tariffs.js";
import { premiumTrafficLimitVisible, regularTrafficLimitVisible } from "./traffic.js";

type WebappRecord = Record<string, unknown>;
type TopupKind = "premium" | "regular";

export type TopupDeeplinkInput = {
  plans: BillingPlan[];
  search: string;
  subscription: WebappRecord;
};

export type RenewalPaymentConfig = {
  defaultMethod: string;
  options: {
    preferCheckout: true;
    preferredTariffKey: string;
    selectDefaultTariff: true;
  };
  plans: BillingPlan[];
  singleTariffMode: boolean;
  subscription: WebappRecord;
  tariffCatalog: TariffCatalogEntry[];
  tariffMode: boolean;
};

function hasActiveTariffSubscription(
  subscription: WebappRecord,
  tariffCatalog: TariffCatalogEntry[],
  tariffMode: boolean
) {
  return Boolean(
    tariffMode &&
    subscription?.active &&
    subscription?.tariff_key &&
    tariffCatalog.some((tariff) => tariff.key === subscription.tariff_key)
  );
}

export function resolveTopupDeeplinkKind({
  plans,
  search,
  subscription,
}: TopupDeeplinkInput): TopupKind | "" {
  const topup = new URLSearchParams(search).get("topup");
  if (topup !== "regular" && topup !== "premium") return "";
  const tariffCatalog = buildTariffCatalog(plans);
  const tariffMode = plans.some((plan) => plan?.tariff_key);
  if (!hasActiveTariffSubscription(subscription, tariffCatalog, tariffMode)) return "";
  const canRegular =
    (subscription?.can_topup_regular_traffic ?? subscription?.can_topup_traffic) &&
    regularTrafficLimitVisible(subscription);
  const canPremium =
    (subscription?.can_topup_premium_traffic ?? subscription?.can_topup_traffic) &&
    premiumTrafficLimitVisible(subscription);
  if (topup === "regular" && canRegular) return "regular";
  if (topup === "premium" && canPremium) return "premium";
  return "";
}

export function renewalPaymentConfig({
  defaultMethod,
  plans,
  subscription,
  tariffKey,
}: {
  defaultMethod: string;
  plans: BillingPlan[];
  subscription: WebappRecord;
  tariffKey: string;
}): RenewalPaymentConfig {
  const tariffCatalog = buildTariffCatalog(plans);
  const tariffMode = plans.some((plan) => plan?.tariff_key);
  return {
    defaultMethod,
    options: {
      preferCheckout: true,
      preferredTariffKey: tariffKey,
      selectDefaultTariff: true,
    },
    plans,
    singleTariffMode: tariffMode && tariffCatalog.length === 1,
    subscription,
    tariffCatalog,
    tariffMode,
  };
}
