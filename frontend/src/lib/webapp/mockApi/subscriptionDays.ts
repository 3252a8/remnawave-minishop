import { DEV_MOCK } from "../previewMock.js";
import { jsonBody } from "../demoMockRuntime.js";
import type { SubscriptionDaysQuote } from "../subscriptionDays.js";
import { DATASET, defaultClone, type DemoRecord } from "./dataset.js";
import { applyDemoDeviceTopup } from "./deviceTopup.js";
import { demoPaymentStatuses, nextDemoPaymentId } from "./state.js";

let initialized = false;
let quoteRevision = 1;
let expiresAt = "2026-12-31T12:00:00Z";
const completedQuotes = new Map<string, number>();
const DAY = 86_400_000;

function mode(): string {
  return typeof window === "undefined"
    ? ""
    : new URLSearchParams(window.location.search).get("subscription_days") || "";
}

function seedHistory(): void {
  if (initialized) return;
  initialized = true;
  if (mode() === "buttons") DEV_MOCK.data.settings.payment_methods_display_mode = "buttons";
  DEV_MOCK.data.subscription = {
    ...DEV_MOCK.data.subscription,
    end_date_text: "31.12.2026 12:00",
  };
  const base =
    DATASET.adminPayments?.find(
      (payment) =>
        Number(payment.user_id) === Number(DEV_MOCK.data.user.user_id || DEV_MOCK.data.user.id)
    ) || DATASET.adminPayments?.[0];
  if (!base) return;
  for (const [index, status] of ["succeeded", "refunded"].entries()) {
    DATASET.adminPayments?.unshift({
      ...base,
      payment_id: 118000 + index,
      user_id: Number(DEV_MOCK.data.user.user_id || DEV_MOCK.data.user.id),
      amount: 0,
      currency: "RUB",
      provider: "subscription_days",
      funding_source: "subscription_days",
      subscription_days_spent: index ? 7 : 4,
      status,
      sale_mode: "hwid_devices",
      purchased_hwid_devices: 1,
      traffic_regular_gb: null,
      traffic_premium_gb: null,
      checkout_discount_amount: 0,
      promo_discount_percent: null,
      description: null,
      promo_code_id: null,
      can_reverse: status === "succeeded",
      can_manual_finalize: false,
      purchases: [{ kind: "hwid_devices", amount: 1, unit: "device", mode: "topup" }],
      created_at: `2026-10-26T1${5 - index}:00:00Z`,
      reversed_at: index ? "2026-10-26T15:00:00Z" : null,
    });
  }
}

function planQuote(plan: DemoRecord, index: number, scenario: string): SubscriptionDaysQuote {
  const eligible = ["eligible", "stale", "panel_failed", "buttons"].includes(scenario);
  const days = (index ? 10 : 4) + (quoteRevision - 1);
  return {
    eligible,
    disabled_reason: eligible ? null : scenario,
    days_to_charge: days,
    current_expires_at: expiresAt,
    next_expires_at: new Date(Date.parse(expiresAt) - days * DAY).toISOString(),
    minimum_remaining_days: 1,
    quote_token: eligible
      ? `demo-days-${quoteRevision}-${plan.sale_mode}-${plan.device_count || plan.traffic_gb || plan.months}`
      : null,
    price_amount: Number(plan.price || 0),
    currency: String(plan.currency || "RUB"),
  };
}

function plansFor(path: string, scenario: string): DemoRecord[] {
  const devices = path.startsWith("/devices");
  const kind = new URLSearchParams(path.split("?")[1] || "").get("kind") || "regular";
  const source = devices ? DEV_MOCK.data.device_topup_options : DEV_MOCK.data.topup_options;
  return ((source?.plans || []) as DemoRecord[])
    .filter((plan) => devices || (kind === "premium") === (plan.sale_mode === "premium_topup"))
    .map((plan, index) => ({ ...plan, subscription_days: planQuote(plan, index, scenario) }));
}

/** Opt-in fixture overlay: ordinary checkout mocks keep their existing behavior. */
export function subscriptionDaysDemoResponse(path: string, options: RequestInit): unknown {
  const scenario = mode();
  if (!scenario) return undefined;
  seedHistory();
  const cleanPath = path.split("?")[0];
  if (cleanPath === "/devices/topup-options" || cleanPath === "/tariffs/topup-options") {
    const devices = cleanPath.startsWith("/devices");
    return {
      ...defaultClone(devices ? DEV_MOCK.data.device_topup_options : DEV_MOCK.data.topup_options),
      ok: true,
      ...(devices
        ? {}
        : { topup_kind: new URLSearchParams(path.split("?")[1]).get("kind") || "regular" }),
      plans: plansFor(path, scenario),
    };
  }
  const reverse = cleanPath.match(/^\/admin\/payments\/(\d+)\/reverse$/);
  if (reverse && options.method === "POST") {
    const payment = DATASET.adminPayments?.find(
      (item) => Number(item.payment_id) === Number(reverse[1])
    );
    if (payment?.provider !== "subscription_days") return undefined;
    sessionStorage.setItem(
      "minishop.demo.subscriptionDaysReverse",
      JSON.stringify(jsonBody(options))
    );
    if (!payment.reversed_at) {
      expiresAt = new Date(
        Date.parse(expiresAt) + Number(payment.subscription_days_spent) * DAY
      ).toISOString();
      payment.reversed_at = new Date().toISOString();
      payment.status = "refunded";
      payment.can_reverse = false;
    }
    return { ok: true, payment: defaultClone(payment) };
  }
  if (cleanPath !== "/payments" || options.method !== "POST") return undefined;
  const body = jsonBody(options);
  if (body.method !== "subscription_days") return undefined;
  const attempts = JSON.parse(
    sessionStorage.getItem("minishop.demo.subscriptionDaysAttempts") || "[]"
  ) as DemoRecord[];
  attempts.push(body);
  sessionStorage.setItem("minishop.demo.subscriptionDaysAttempts", JSON.stringify(attempts));
  const token = String(body.quote_token || "");
  const previous = completedQuotes.get(token);
  if (previous) return { ok: true, action: "completed", paid: true, payment_id: previous };
  if (scenario === "stale" && quoteRevision === 1) {
    quoteRevision += 1;
    return { ok: false, error: "subscription_days_quote_stale" };
  }
  if (scenario === "panel_failed") return { ok: false, error: "subscription_days_panel_failed" };
  const devices = String(body.sale_mode).startsWith("hwid_device");
  const kind = body.sale_mode === "premium_topup" ? "premium" : "regular";
  const plans = plansFor(
    devices ? "/devices/topup-options" : `/tariffs/topup-options?kind=${kind}`,
    scenario
  );
  const plan = plans.find(
    (item) => (item.subscription_days as SubscriptionDaysQuote).quote_token === token
  );
  if (!plan || !token) return { ok: false, error: "subscription_days_quote_stale" };
  const quote = plan.subscription_days as SubscriptionDaysQuote;
  if (!quote.eligible) return { ok: false, error: "subscription_days_unavailable" };
  expiresAt = String(quote.next_expires_at);
  if (devices) applyDemoDeviceTopup(Number(body.device_count || body.months));
  const date = new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" }).format(
    new Date(expiresAt)
  );
  DEV_MOCK.data.subscription = {
    ...DEV_MOCK.data.subscription,
    end_date_text: date,
    ...(devices ? { extra_hwid_devices_valid_until_text: date } : {}),
  };
  const paymentId = nextDemoPaymentId();
  completedQuotes.set(token, paymentId);
  demoPaymentStatuses.set(String(paymentId), {
    status: "succeeded",
    paid: true,
    sale_mode: String(body.sale_mode),
    device_count: Number(body.device_count || 0),
    applied: true,
  });
  const base = DATASET.adminPayments?.find((item) => item.provider === "subscription_days");
  if (base)
    DATASET.adminPayments?.unshift({
      ...base,
      payment_id: paymentId,
      status: "succeeded",
      can_reverse: true,
      reversed_at: null,
      created_at: new Date().toISOString(),
      subscription_days_spent: quote.days_to_charge,
      sale_mode: body.sale_mode,
      purchased_hwid_devices: devices ? Number(body.device_count) : null,
      purchased_gb: devices ? null : Number(body.traffic_gb),
      purchases: devices
        ? [
            {
              kind: "hwid_devices",
              amount: Number(body.device_count),
              unit: "device",
              mode: "topup",
            },
          ]
        : [
            {
              kind: "traffic",
              amount: Number(body.traffic_gb),
              unit: "gb",
              scope: kind,
              mode: "topup",
            },
          ],
    });
  quoteRevision += 1;
  return { ok: true, action: "completed", paid: true, payment_id: paymentId };
}
