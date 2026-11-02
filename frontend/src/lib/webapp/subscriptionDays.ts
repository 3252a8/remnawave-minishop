import type { PaymentMethod } from "./tariffs.js";
import type { DeviceTopupOptions, Translate } from "./types.js";

export const SUBSCRIPTION_DAYS_METHOD = "subscription_days";

export type SubscriptionDaysQuote = NonNullable<
  NonNullable<DeviceTopupOptions["plans"]>[number]["subscription_days"]
>;

export function subscriptionDaysQuote(plan: unknown): SubscriptionDaysQuote | null {
  if (!plan || typeof plan !== "object" || !("subscription_days" in plan)) return null;
  const quote = plan.subscription_days;
  return quote && typeof quote === "object" && "eligible" in quote
    ? (quote as SubscriptionDaysQuote)
    : null;
}

export function subscriptionDaysQuoteUsable(quote: SubscriptionDaysQuote | null): boolean {
  return Boolean(
    quote?.eligible &&
    Number.isInteger(quote.days_to_charge) &&
    Number(quote.days_to_charge) > 0 &&
    quote.quote_token &&
    quote.current_expires_at &&
    quote.next_expires_at &&
    Number.isFinite(Date.parse(quote.next_expires_at)) &&
    Date.parse(quote.next_expires_at) < Date.parse(quote.current_expires_at)
  );
}

const disabledReasons = new Set([
  "subscription_required",
  "paid_subscription_required",
  "duration_required",
  "recurring_conflict",
  "price_unavailable",
  "insufficient_days",
  "package_unavailable",
]);

export function subscriptionDaysDisabledReason(quote: SubscriptionDaysQuote, t: Translate): string {
  const reason = disabledReasons.has(String(quote.disabled_reason))
    ? quote.disabled_reason
    : "package_unavailable";
  return t(`wa_subscription_days_${reason}`, { days: quote.minimum_remaining_days });
}

export function withSubscriptionDaysMethod(
  methods: PaymentMethod[],
  plan: unknown,
  t: Translate
): PaymentMethod[] {
  const quote = subscriptionDaysQuote(plan);
  if (!quote) return methods;
  const disabled = !subscriptionDaysQuoteUsable(quote);
  return [
    ...methods.filter((method) => method.id !== SUBSCRIPTION_DAYS_METHOD),
    {
      id: SUBSCRIPTION_DAYS_METHOD,
      name: t("wa_subscription_days_method"),
      icon: "CalendarDays",
      balance_supported: false,
      disabled,
      disabled_reason: String(quote.disabled_reason || ""),
      disabled_message: disabled ? subscriptionDaysDisabledReason(quote, t) : "",
    },
  ];
}

export function subscriptionDaysRequestError(error: unknown): string {
  if (!error || typeof error !== "object" || !("error" in error)) return "";
  const code = String(error.error || "");
  return [
    "subscription_days_quote_stale",
    "subscription_days_unavailable",
    "subscription_days_panel_failed",
    "invalid_subscription_days_purchase",
  ].includes(code)
    ? code
    : "";
}
