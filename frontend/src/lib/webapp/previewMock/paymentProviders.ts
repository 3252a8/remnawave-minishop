import { DATASET } from "../mockApi/dataset.js";
import { DEV_MOCK } from "./devMock";
import { createI18n } from "../i18n.js";
import en from "../../../../../locales/en.json";
import ru from "../../../../../locales/ru.json";

export const PAYMENT_PROVIDER_DEMO_METHODS = [
  { id: "anore", name: "Anore", icon: "CreditCard" },
  { id: "cryptomus", name: "Cryptomus", icon: "Bitcoin" },
  { id: "cispay", name: "CisPay", icon: "CreditCard" },
  {
    id: "cryptomus_subscription",
    name: "Cryptomus subscription",
    icon: "Bitcoin",
    labelKey: "payment_provider_cryptomus_subscription_webapp_label",
  },
  {
    id: "cispay_subscription_card",
    name: "Card subscription",
    icon: "CreditCard",
    labelKey: "payment_provider_cispay_subscription_card_webapp_label",
  },
  {
    id: "cispay_subscription_sbp",
    name: "SBP subscription",
    icon: "CreditCard",
    labelKey: "payment_provider_cispay_subscription_sbp_webapp_label",
  },
];

/** Exercise hosted providers in the existing checkout and payment-history preview. */
export function applyPaymentProvidersDemo(): void {
  const { t } = createI18n({
    messages: { ru, en },
    defaultLang: String(DEV_MOCK.config.language || "ru"),
  });
  DEV_MOCK.data.payment_provider_demo = true;
  DEV_MOCK.data.payment_methods = [
    ...DEV_MOCK.data.payment_methods.filter(
      (method) => !PAYMENT_PROVIDER_DEMO_METHODS.some((provider) => provider.id === method.id)
    ),
    ...PAYMENT_PROVIDER_DEMO_METHODS.map((method) => ({
      ...method,
      name: method.labelKey ? t(method.labelKey, {}, method.name) : method.name,
    })),
  ];
  const methodIds = PAYMENT_PROVIDER_DEMO_METHODS.map((method) => method.id);
  for (const plan of DEV_MOCK.data.plans) {
    if (Array.isArray(plan.available_payment_method_ids)) {
      plan.available_payment_method_ids = [...plan.available_payment_method_ids, ...methodIds];
    }
  }
  const userId = DEV_MOCK.data.user.user_id ?? DEV_MOCK.data.user.id;
  for (const [index, method] of PAYMENT_PROVIDER_DEMO_METHODS.entries()) {
    const payment = DATASET.adminPayments?.[index];
    if (!payment) continue;
    Object.assign(payment, {
      provider: method.id,
      user_id: userId,
      status: "succeeded",
      created_at: `2031-04-12T12:00:0${6 - index}Z`,
    });
  }
}
