import type { BillingPlan } from "./tariffs.js";

type WebappRecord = Record<string, unknown>;
type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

type PrimaryPaySubscription = WebappRecord & {
  active?: boolean;
};

type PrimaryPayActionLabelInput = {
  appSettings: WebappRecord | null | undefined;
  selectedPlan: BillingPlan | null | undefined;
  subscription: PrimaryPaySubscription | null | undefined;
  t: Translate;
  trafficMode: boolean;
};

type PrimaryPayActionLabelDeps = {
  getAppSettings: () => WebappRecord | null | undefined;
  getSelectedPlan: () => BillingPlan | null | undefined;
  getSubscription: () => PrimaryPaySubscription | null | undefined;
  getTrafficMode: () => boolean;
  t: Translate;
};

const PAY_FULL_SUBSCRIPTION_FALLBACK =
  "\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c \u043f\u043e\u043b\u043d\u0443\u044e \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443";
const RENEW_SUBSCRIPTION_FALLBACK =
  "\u041f\u0440\u043e\u0434\u043b\u0438\u0442\u044c \u043f\u043e\u0434\u043f\u0438\u0441\u043a\u0443";

export function resolvePrimaryPayActionLabel({
  appSettings,
  selectedPlan,
  subscription,
  t,
  trafficMode,
}: PrimaryPayActionLabelInput) {
  if (!subscription?.active && appSettings?.trial_enabled && appSettings?.trial_available) {
    return t("wa_pay_full_subscription", {}, PAY_FULL_SUBSCRIPTION_FALLBACK);
  }
  if (trafficMode || selectedPlan?.sale_mode === "traffic_package") return t("wa_buy_traffic");
  return subscription?.active
    ? t("wa_renew_subscription", {}, RENEW_SUBSCRIPTION_FALLBACK)
    : t("wa_pay_subscription");
}

export function createPrimaryPayActionLabel({
  getAppSettings,
  getSelectedPlan,
  getSubscription,
  getTrafficMode,
  t,
}: PrimaryPayActionLabelDeps) {
  return function primaryPayActionLabel() {
    return resolvePrimaryPayActionLabel({
      appSettings: getAppSettings(),
      selectedPlan: getSelectedPlan(),
      subscription: getSubscription(),
      t,
      trafficMode: getTrafficMode(),
    });
  };
}
