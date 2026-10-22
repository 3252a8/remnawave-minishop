import { DEV_MOCK } from "../previewMock.js";
import { jsonBody } from "../demoMockRuntime.js";
import { currentDemoBalance } from "./balance.js";
import ru from "../../../../../locales/ru.json";
import en from "../../../../../locales/en.json";

/** An opt-in demo failure stays entirely inside the existing mock API. */
export function paymentFallbackDemoResponse(path: string, options: RequestInit): unknown {
  const scenario = new URLSearchParams(window.location.search).get("payment_failure");
  if (!scenario) return undefined;
  if (path === "/me") {
    const locale = DEV_MOCK.config.language === "en" ? en : ru;
    const recurring = scenario === "contacts";
    const cryptoMethods = [
      {
        id: "cryptopay",
        name: "Crypto Pay",
        icon: "Bitcoin",
        group: "crypto",
        provider_id: "cryptopay_service",
      },
      {
        id: "cryptopay_bot",
        name: "Crypto Pay Bot",
        icon: "Bitcoin",
        group: "crypto",
        provider_id: "cryptopay_service",
      },
      {
        id: "cryptomus",
        name: "Cryptomus",
        icon: "Bitcoin",
        group: "crypto",
        provider_id: "cryptomus_service",
      },
    ];
    DEV_MOCK.data.payment_methods = [
      ...(scenario === "crypto" ? [cryptoMethods[0]] : []),
      {
        id: recurring ? "wata_subscription" : "wata",
        name: "WATA",
        icon: "CreditCard",
        balance_supported: !recurring,
        group: scenario === "unknown" ? null : "fiat",
        provider_id: "wata_service",
      },
      ...(scenario === "only"
        ? []
        : [
            ...(scenario === "crypto" ? [cryptoMethods[1]] : [cryptoMethods[0]]),
            {
              id: "wata_card",
              name: "WATA Card",
              icon: "CreditCard",
              group: "fiat",
              provider_id: "wata_service",
            },
            {
              id: "cloudpayments",
              name: "CloudPayments",
              icon: "CreditCard",
              min_amount: 5000,
              min_currency: "RUB",
              group: "fiat",
              provider_id: "cloudpayments_service",
            },
            {
              id: "stars",
              name: "Telegram Stars",
              icon: "Star",
              group: "stars",
              provider_id: "telegram_stars",
            },
            {
              id: "platega_sbp",
              name: locale.wa_partner_method_sbp,
              icon: "Smartphone",
              group: "fiat",
              provider_id: "platega_service",
            },
            cryptoMethods[2],
            {
              id: "platega_card",
              name: "Platega Card",
              icon: "CreditCard",
              group: "fiat",
              provider_id: "platega_service",
            },
          ]),
    ];
    const ids = DEV_MOCK.data.payment_methods.map((method) => method.id);
    for (const plan of DEV_MOCK.data.plans) plan.available_payment_method_ids = ids;
    DEV_MOCK.data.settings.user_balance_enabled = true;
    const balance = currentDemoBalance();
    balance.enabled = true;
    balance.sources = ["user", "partner"].map((id) => ({
      id,
      available: true,
      recurring_available: true,
      amount_minor: 10000,
    }));
    DEV_MOCK.data.balance = { ...DEV_MOCK.data.balance, ...balance };
  }
  if (
    !["/payments", "/balance/topup", "/tariffs/change-payment"].includes(path) ||
    options.method !== "POST"
  )
    return undefined;
  const key = "minishop.demo.paymentFallbackAttempts";
  const attempts = JSON.parse(sessionStorage.getItem(key) || "[]") as unknown[];
  attempts.push(jsonBody(options));
  sessionStorage.setItem(key, JSON.stringify(attempts));
  if (scenario === "validation")
    return { ok: false, error: "invalid_plan", message: "Invalid plan" };
  throw Object.assign(new Error("service_unavailable"), {
    status: 502,
    payload: { ok: false, error: "payment_provider_unavailable" },
  });
}
