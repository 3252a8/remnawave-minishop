import {
  activeTariffName,
  buildTariffCatalog,
  type BillingPlan,
  type TariffCatalogEntry,
} from "./tariffs.js";
import {
  premiumTrafficLimitVisible,
  premiumTrafficPercent,
  regularTrafficLimitVisible,
  trafficPercent,
} from "./traffic.js";

type WebappRecord = Record<string, unknown>;

type BillingSubscription = BillingPlan & {
  active?: boolean;
  can_topup_premium_traffic?: boolean;
  can_topup_regular_traffic?: boolean;
  can_topup_traffic?: boolean;
  premium_limit_bytes?: number | string;
  premium_topup_always_available?: boolean;
  premium_unlimited_override?: boolean;
  premium_used_bytes?: number | string;
  regular_unlimited_override?: boolean;
  topup_always_available?: boolean;
  traffic_limit_bytes?: number | string;
  traffic_used_bytes?: number | string;
};

export interface BillingView {
  activeTariffCatalogEntry: TariffCatalogEntry | null;
  canChangeTariff: boolean;
  canOpenPremiumTopupModal: boolean;
  canOpenRegularTopupModal: boolean;
  currentTariffName: string;
  hasActiveTariffSubscription: boolean;
  hasMultipleTariffs: boolean;
  premiumTrafficTopupBarClickable: boolean;
  premiumTrafficTopupUnlocked: boolean;
  regularTrafficTopupBarClickable: boolean;
  regularTrafficTopupUnlocked: boolean;
  selectedTariff: TariffCatalogEntry | null;
  selectedTariffPlans: BillingPlan[];
  singleTariffMode: boolean;
  subscriptionIsTrafficTariff: boolean;
  tariffCatalog: TariffCatalogEntry[];
  tariffMode: boolean;
  trafficMode: boolean;
}

export interface BillingViewInput {
  appSettings: WebappRecord | null | undefined;
  plans: BillingPlan[];
  selectedTariffKey: string;
  subscription: BillingSubscription;
  topupUnlockPercent: number;
}

export function computeBillingView({
  appSettings,
  plans,
  selectedTariffKey,
  subscription,
  topupUnlockPercent,
}: BillingViewInput): BillingView {
  const trafficMode = Boolean(appSettings?.traffic_mode);
  const tariffMode = plans.some((plan) => plan?.tariff_key);
  const tariffCatalog = buildTariffCatalog(plans);
  const singleTariffMode = tariffMode && tariffCatalog.length === 1;
  const hasMultipleTariffs = tariffCatalog.length > 1;
  const selectedTariff = tariffCatalog.find((tariff) => tariff.key === selectedTariffKey) || null;
  const selectedTariffPlans = tariffMode
    ? selectedTariffKey
      ? plans.filter((plan) => plan?.tariff_key === selectedTariffKey)
      : []
    : plans;
  const hasActiveTariffSubscription = Boolean(
    tariffMode && subscription?.active && subscription?.tariff_key
  );
  const canChangeTariff = Boolean(hasActiveTariffSubscription && hasMultipleTariffs);
  const currentTariffName = activeTariffName(subscription, plans);
  const canOpenRegularTopupModal = Boolean(
    hasActiveTariffSubscription &&
    (subscription?.can_topup_regular_traffic ?? subscription?.can_topup_traffic) &&
    regularTrafficLimitVisible(subscription)
  );
  const canOpenPremiumTopupModal = Boolean(
    hasActiveTariffSubscription &&
    (subscription?.can_topup_premium_traffic ?? subscription?.can_topup_traffic) &&
    premiumTrafficLimitVisible(subscription)
  );
  const activeTariffCatalogEntry =
    tariffCatalog.find((entry) => entry.key === String(subscription?.tariff_key || "").trim()) ||
    null;
  const subscriptionIsTrafficTariff = Boolean(
    String(
      subscription?.billing_model || activeTariffCatalogEntry?.billing_model || ""
    ).toLowerCase() === "traffic"
  );
  const regularTrafficUsagePercent = trafficPercent(subscription);
  const premiumTrafficUsagePercent = premiumTrafficPercent(subscription);
  // Admin toggles on the tariff: skip the usage threshold per traffic type.
  const regularEffectiveUnlockPercent = subscription?.topup_always_available
    ? 0
    : topupUnlockPercent;
  const premiumEffectiveUnlockPercent = subscription?.premium_topup_always_available
    ? 0
    : topupUnlockPercent;
  const regularTrafficTopupUnlocked = Boolean(
    canOpenRegularTopupModal && regularTrafficUsagePercent >= regularEffectiveUnlockPercent
  );
  const premiumTrafficTopupUnlocked = Boolean(
    canOpenPremiumTopupModal && premiumTrafficUsagePercent >= premiumEffectiveUnlockPercent
  );
  const regularTrafficTopupBarClickable = Boolean(
    canOpenRegularTopupModal &&
    (subscriptionIsTrafficTariff || regularTrafficUsagePercent >= regularEffectiveUnlockPercent)
  );
  const premiumTrafficTopupBarClickable = Boolean(
    canOpenPremiumTopupModal &&
    (subscriptionIsTrafficTariff || premiumTrafficUsagePercent >= premiumEffectiveUnlockPercent)
  );

  return {
    activeTariffCatalogEntry,
    canChangeTariff,
    canOpenPremiumTopupModal,
    canOpenRegularTopupModal,
    currentTariffName,
    hasActiveTariffSubscription,
    hasMultipleTariffs,
    premiumTrafficTopupBarClickable,
    premiumTrafficTopupUnlocked,
    regularTrafficTopupBarClickable,
    regularTrafficTopupUnlocked,
    selectedTariff,
    selectedTariffPlans,
    singleTariffMode,
    subscriptionIsTrafficTariff,
    tariffCatalog,
    tariffMode,
    trafficMode,
  };
}
