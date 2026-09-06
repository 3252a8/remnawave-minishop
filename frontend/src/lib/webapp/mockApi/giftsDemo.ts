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

export function giftsDemoResponse(path: string, options: RequestInit, fullPath = path): unknown {
  const demoGiftsEnabled = DEV_MOCK.config.giftsEnabled !== false;
  const demo = new URLSearchParams(window.location.search).get("gift_demo");
  if (path === "/admin/gifts") {
    const params = new URLSearchParams(fullPath.split("?")[1] || "");
    const rows = Array.from({ length: 57 }, (_, index) => ({
      ...gifts[index % gifts.length],
      gift_id: 4101 - index,
      payment_id: 4101 - index,
      created_at: new Date(Date.UTC(2026, 8, 5) - index * 3600000).toISOString(),
      tariff_title: index % 3 ? "Premium" : "Standard",
    }))
      .map((item, index) => ({
        ...item,
        link: null,
        purchaser_id: 101 + index,
        purchaser_label: index ? "anna@example.com" : "alex",
        recipient_id: item.status === "activated" ? 207 : null,
        recipient_label: "maria",
        amount: 1090 + index * 10,
        total_amount: 1490 + index * 10,
        currency: "RUB",
        provider: "yookassa",
        payment_status: "succeeded",
        user_balance_amount: 250,
        partner_balance_amount: 150,
        discount_amount: 160,
        promo_code_id: 14,
        delivery_attempts: 1,
      }))
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
      enabled: demoGiftsEnabled && demo !== "disabled",
      gifts:
        demo === "empty"
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
