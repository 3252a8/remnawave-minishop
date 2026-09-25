import type { components } from "$lib/api/openapi.generated.js";
import type { GiftView } from "../gifts.svelte.js";
import type { DemoRecord } from "./dataset";
import { DEV_MOCK } from "../previewMock.js";
import { jsonBody } from "../demoMockRuntime.js";

const gift = (id: number, status = "ready"): GiftView => ({
  gift_id: id,
  payment_id: id,
  status,
  tariff_title: "Premium",
  duration_days: 90,
  devices: 5,
  regular_limit_gb: 250,
  premium_limit_gb: 50,
  premium_unlimited: false,
  created_at: "2026-09-05T12:00:00Z",
  activated_at: status === "activated" ? "2026-09-05T13:00:00Z" : null,
  activation_end_at: null,
  link: status === "ready" ? `https://example.com/?gift=${"R".repeat(43)}` : null,
  owned: true,
  claimed_by_me: false,
  conflict: "",
  bonus_days: 7,
  regular_bonus_gb: 10,
  premium_bonus_gb: 0,
  recipient_email: "friend@example.com",
  delivery_status: "sent",
  delivered_at: "2026-09-05T12:01:00Z",
  extends_subscription: false,
});
let gifts = [gift(4101), gift(4100, "activated")];
const claimed = new Set<string>();
let nextId = 4200;
type AdminGift = components["schemas"]["AdminGiftView"];
const adminCreated: AdminGift[] = [];
const adminRequests = new Map<string, AdminGift>();
export function adminGiftDemoStats() {
  return { admin_gifts_count: 12 + adminCreated.length, admin_gifts_activated_count: 8 };
}
function adminGiftRows(): AdminGift[] {
  return Array.from({ length: 57 }, (_, index) => ({
    ...gift(4101 - index, index % 2 ? "activated" : "ready"),
    link: null,
    created_at: new Date(Date.UTC(2026, 8, 5) - index * 3600000).toISOString(),
    tariff_title: index % 3 ? "Premium" : "Standard",
    purchaser_id: 101 + index,
    purchaser_minishop_id: `ms_${String(101 + index).padStart(32, "0")}`,
    purchaser_label: index ? "anna@example.com" : "alex",
    recipient_id: index % 2 ? 207 : null,
    recipient_minishop_id: index % 2 ? `ms_${String(207).padStart(32, "0")}` : null,
    recipient_label: index % 2 ? "maria" : "",
    amount: index === 2 ? 0 : 1090 + index * 10,
    total_amount: index === 2 ? 0 : 1490 + index * 10,
    currency: "RUB",
    provider: index === 2 ? "admin_gift" : "yookassa",
    payment_status: "succeeded",
    user_balance_amount: index === 2 ? 0 : 250,
    partner_balance_amount: index === 2 ? 0 : 150,
    discount_amount: index === 2 ? 0 : 160,
    promo_code_id: index === 2 ? null : 14,
    delivery_attempts: 1,
    balance_enabled: DEV_MOCK.config.userBalanceEnabled !== false,
  }));
}

export function giftsDemoResponse(path: string, options: RequestInit, fullPath = path): unknown {
  const demo = new URLSearchParams(window.location.search).get("gift_demo");
  const demoGiftsEnabled =
    DEV_MOCK.config.giftsEnabled !== false && !["disabled", "disabled-empty"].includes(demo || "");
  if (path === "/gifts" && demo === "loading") return new Promise(() => {});
  if (path === "/gifts" && demo === "error") throw new Error("Gift list unavailable");
  if (/^\/admin\/payments\/\d+$/.test(path)) {
    const row = [...adminCreated, ...adminGiftRows()].find(
      (item) => item.provider === "admin_gift" && item.payment_id === Number(path.split("/").pop())
    );
    if (row)
      return {
        ok: true,
        payment: {
          payment_id: row.payment_id,
          user_id: row.purchaser_id,
          user_label: row.purchaser_label,
          provider: "admin_gift",
          funding_source: "admin_grant",
          amount: 0,
          currency: row.currency,
          status: "succeeded",
          created_at: row.created_at,
          fulfilled_at: row.created_at,
          fulfilled_by_admin_id: row.purchaser_id,
          fulfillment_source: "admin",
          subscription_duration_days: row.duration_days,
          subscription_duration_months: null,
          tariff_key: "standard",
          sale_mode: `subscription@standard|d${row.duration_days}|gift`,
          checkout_total_amount: 0,
          checkout_base_amount: 0,
          checkout_discount_amount: 0,
          user_balance_amount: 0,
          partner_balance_amount: 0,
          promo_code_id: null,
          can_manual_finalize: false,
          can_reverse: false,
          purchases: [],
        },
      };
  }
  if (path === "/admin/gifts/options")
    return {
      ok: true,
      email_available: true,
      plans: (DEV_MOCK.data.plans as DemoRecord[])
        .filter((p) => !p.sale_mode || p.sale_mode === "subscription")
        .map((p) => ({
          ...p,
          effective_hwid_device_limit: p.effective_hwid_device_limit ?? p.hwid_device_limit ?? 5,
        })),
    };
  if (path === "/admin/gifts" && options.method === "POST") {
    const body = jsonBody(options);
    const previous = adminRequests.get(String(body.request_id));
    if (previous) return { ok: true, gift: previous };
    const plan = (DEV_MOCK.data.plans as DemoRecord[]).find((p) => String(p.id) === body.plan_id);
    if (!plan) return { ok: false, error: "invalid_plan" };
    const addons = (body.checkout_addons || {}) as DemoRecord;
    const created: AdminGift = {
      ...adminGiftRows()[2],
      ...gift(++nextId),
      tariff_title: String(plan.tariff_name || plan.title),
      duration_days: Number(plan.duration_days || Number(plan.months) * 30),
      created_at: new Date().toISOString(),
      activated_at: null,
      recipient_id: null,
      recipient_label: "",
      purchaser_id: 1,
      purchaser_label: "admin",
      amount: 0,
      total_amount: 0,
      currency: String(plan.currency || "RUB"),
      provider: "admin_gift",
      user_balance_amount: 0,
      partner_balance_amount: 0,
      discount_amount: 0,
      promo_code_id: null,
      bonus_days: 0,
      regular_bonus_gb: 0,
      devices:
        Number(plan.effective_hwid_device_limit ?? plan.hwid_device_limit ?? 5) +
        Number(addons.device_count || 0),
      regular_limit_gb: Number(addons.regular_limit_gb ?? plan.monthly_gb ?? 0),
      premium_limit_gb: Number(addons.premium_limit_gb ?? plan.premium_monthly_gb ?? 0),
      recipient_email: String(body.recipient_email || "") || null,
      delivery_status: body.recipient_email ? "pending" : "not_requested",
      delivered_at: null,
      delivery_attempts: 0,
    };
    adminCreated.unshift(created);
    adminRequests.set(String(body.request_id), created);
    return { ok: true, gift: created };
  }
  if (/^\/admin\/gifts\/\d+$/.test(path)) {
    const row = [...adminCreated, ...adminGiftRows()].find(
      (item) => item.gift_id === Number(path.split("/").pop())
    );
    return row
      ? {
          ok: true,
          gift: {
            ...row,
            link:
              row.provider === "admin_gift" && row.status === "ready"
                ? row.link || `https://example.com/?gift=${"R".repeat(43)}`
                : null,
          },
        }
      : { ok: false, error: "gift_unavailable" };
  }
  if (/^\/admin\/gifts\/\d+\/revoke$/.test(path)) {
    const giftId = Number(path.split("/")[3]);
    const row = [...adminCreated, ...adminGiftRows()].find((item) => item.gift_id === giftId);
    if (!row || row.status !== "ready" || row.payment_status !== "succeeded")
      return { ok: false, error: "gift_revoke_unavailable" };
    const revoked = { ...row, status: "revoked", link: null };
    const createdIndex = adminCreated.findIndex((item) => item.gift_id === giftId);
    if (createdIndex >= 0) adminCreated[createdIndex] = revoked;
    return { ok: true, gift: revoked };
  }
  if (path === "/admin/gifts") {
    const params = new URLSearchParams(fullPath.split("?")[1] || "");
    const rows = [...adminCreated, ...adminGiftRows()]
      .filter(
        (item) =>
          !params.get("source") ||
          (item.provider === "admin_gift" ? "admin" : "purchase") === params.get("source")
      )
      .filter((item) => !params.get("status") || item.status === params.get("status"))
      .filter(
        (item) =>
          !params.get("q") ||
          JSON.stringify(item)
            .toLowerCase()
            .includes(String(params.get("q")).toLowerCase())
      );
    const [key, direction] = (params.get("sort") || "date_desc").split("_");
    const fields: Record<string, keyof (typeof rows)[number]> = {
      id: "gift_id",
      buyer: "purchaser_label",
      recipient: "recipient_label",
      tariff: "tariff_title",
      amount: "total_amount",
      provider: "provider",
      status: "status",
      date: "created_at",
    };
    const field = fields[key] || "gift_id";
    rows.sort(
      (a, b) =>
        (typeof a[field] === "number"
          ? Number(a[field]) - Number(b[field])
          : String(a[field]).localeCompare(String(b[field]))) * (direction === "asc" ? 1 : -1)
    );
    const page = Number(params.get("page") || 0);
    return { ok: true, gifts: rows.slice(page * 25, (page + 1) * 25), total: rows.length };
  }
  if (path === "/gifts")
    return {
      ok: true,
      enabled: demoGiftsEnabled,
      gifts:
        demo === "empty" || demo === "disabled-empty"
          ? []
          : gifts.map((item) =>
              demo === "email-failed" && item.status === "ready"
                ? { ...item, delivery_status: "failed", delivered_at: null }
                : item
            ),
    };
  if (path === "/gifts/options")
    return {
      ok: true,
      email_available: true,
      enabled: demoGiftsEnabled && demo !== "disabled",
      plans: (DEV_MOCK.data.plans as DemoRecord[]).filter(
        (plan) => !plan.sale_mode || plan.sale_mode === "subscription"
      ),
    };
  if (path === "/payments" && jsonBody(options).gift) {
    if (!demoGiftsEnabled || demo === "disabled")
      return { ok: false, error: "gift_purchase_unavailable" };
    const body = jsonBody(options);
    const plan = (DEV_MOCK.data.plans as DemoRecord[]).find(
      (item) =>
        item.tariff_key === body.tariff_key &&
        Number(item.duration_days || Number(item.months) * 30) ===
          Number(body.duration_days || Number(body.months) * 30)
    );
    const created = {
      ...gift(++nextId),
      tariff_title: String(plan?.tariff_name || "Premium"),
      duration_days: Number(body.duration_days || Number(body.months) * 30 || 90),
      recipient_email: String(body.gift_recipient_email || "") || null,
      delivery_status: body.gift_recipient_email ? "pending" : "not_requested",
      delivered_at: null,
      bonus_days: body.promo_code ? 7 : 0,
      regular_bonus_gb: 0,
    };
    if (demo === "pending")
      return {
        ok: true,
        action: "invoice_sent",
        payment_id: created.payment_id,
        payment_url: "https://example.com/payment",
      };
    gifts = [created, ...gifts];
    return { ok: true, action: "completed", paid: true, payment_id: created.payment_id };
  }
  if (path.startsWith("/payments/42"))
    return {
      ok: true,
      paid: demo !== "pending",
      status: demo === "pending" ? "pending" : "succeeded",
    };
  if (path === "/gifts/preview" || path === "/gifts/claim") {
    const token = String(jsonBody(options).token || "");
    if (token.startsWith("X")) return { ok: false, error: "gift_not_found" };
    if (path === "/gifts/claim") {
      if (token.startsWith("F")) return { ok: false, error: "gift_activation_retry" };
      if (token.startsWith("T"))
        return new Promise((resolve) =>
          window.setTimeout(() => {
            claimed.add(token);
            resolve({ ok: true });
          }, 3000)
        );
      claimed.add(token);
      return { ok: true };
    }
    const status =
      token.startsWith("U") || token.startsWith("A") || claimed.has(token)
        ? "activated"
        : token.startsWith("V")
          ? "revoked"
          : "ready";
    return {
      ok: true,
      gift: {
        ...gift(5100, status),
        owned: token.startsWith("O"),
        extends_subscription: token.startsWith("E"),
        recipient_email: null,
        delivery_status: null,
        link: null,
        claimed_by_me: token.startsWith("A") || claimed.has(token),
        conflict: token.startsWith("C")
          ? "gift_tariff_conflict"
          : token.startsWith("M")
            ? "gift_recurring_conflict"
            : "",
      },
    };
  }
  return undefined;
}
