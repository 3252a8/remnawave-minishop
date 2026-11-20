import { previewPeriodPlan } from "./devMock";

export const DEMO_CHECKOUT_PROMO_CODE = "DEMO20";

export function demoCheckoutPlans() {
  return [
    previewPeriodPlan(1, 290, 145, "1 месяц"),
    previewPeriodPlan(3, 790, 395, "3 месяца"),
    previewPeriodPlan(6, 1490, 745, "6 месяцев"),
    previewPeriodPlan(12, 2690, 1345, "1 год"),
  ];
}

export function demoCheckoutMethods() {
  return [
    {
      id: "cloudpayments",
      name: "CloudPayments",
      icon: "CreditCard",
      min_amount: 500,
      min_currency: "RUB",
    },
    { id: "yookassa", name: "Карта", icon: "CreditCard" },
    { id: "platega_sbp", name: "СБП", icon: "Smartphone" },
    { id: "stars", name: "Telegram Stars", icon: "Star" },
    { id: "cryptopay", name: "Криптовалюта", icon: "Bitcoin" },
  ];
}
