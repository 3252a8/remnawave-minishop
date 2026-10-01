import type { components } from "../../api/openapi.generated";
import { demoAds, demoPromos } from "./state";

type Detail = components["schemas"]["AdDetailOut"];
const cards = new Map<number, Detail>();
const date = (days = 0) => new Date(Date.now() - days * 86400000).toISOString();

function card(id: number): Detail {
  const cached = cards.get(id);
  if (cached) return cached;
  const ad = demoAds().find((item) => Number(item.id) === id);
  const value: Detail = {
    campaign: {
      id,
      source: String(ad?.source || "QA campaign"),
      start_param: String(ad?.start_param || "qa_ads"),
      name: "QA · Advertising",
      cost: Number(ad?.cost || 4500),
      is_active: true,
      created_at: date(100),
      advertiser_id: null,
      stats_reset_at: null,
      archived_at: null,
      stats: {
        starts: 3,
        trials: 1,
        payers: 1,
        revenue: 900,
        revenue_by_currency: { RUB: 900, XTR: 49 },
      },
    },
    name: "QA · Advertising",
    description: "Synthetic demonstration data",
    archived_at: null,
    legacy_urls: {},
    legacy_warning: null,
    report_currency: "RUB",
    attribution_window_days: 30,
    spend_source: "manual",
    report: {
      contacts: 3,
      attributed_users: 2,
      registrations: 1,
      returning_users: 1,
      trials: 1,
      payers: 1,
      first_payers: 1,
      purchases: 2,
      period_mode: "events",
      legacy_payment_count: 0,
      platform: { impressions: 1000, clicks: 50, starts: 20 },
      ctr: 0.05,
      registration_conversion: 0.333,
      mature_cohorts: { "7": 1, "30": 1, "90": 0 },
      currencies: [
        {
          currency: "RUB",
          scale: 2,
          cash_minor: "140000",
          product_minor: "160000",
          refund_minor: "70000",
          net_minor: "90000",
          first_purchase_minor: "90000",
          repeat_purchase_minor: "70000",
          spend_minor: "450000",
          purchases: 2,
          roas: 0.2,
          cac_minor: 450000,
          average_order_minor: 80000,
          d7_minor: "90000",
          d30_minor: "90000",
          d90_minor: "0",
        },
      ],
    },
    links: [
      {
        id: 1,
        code: "ad_demo_channel",
        label: "QA · Channel",
        destination: "web",
        landing_path: "/",
        utm: { utm_source: "telegram", utm_medium: "paid", utm_campaign: "qa" },
        is_active: true,
        urls: {
          web: "https://shop.example.test/?campaign=ad_demo_channel&utm_source=telegram",
          bot: "https://t.me/example_bot?start=ad_demo_channel",
          miniapp: "https://t.me/example_bot?startapp=ad_demo_channel",
        },
      },
    ],
    bindings: [],
    spends: [
      {
        id: 1,
        amount_minor: "450000",
        currency: "RUB",
        scale: 2,
        occurred_at: date(35),
        source: "manual",
        note: "QA · Synthetic expense",
      },
    ],
    touches: [
      {
        id: 1,
        user_id: 910000002,
        original_user_id: null,
        channel: "web",
        evidence: "tagged_link",
        occurred_at: date(35),
        received_at: date(35),
        is_new_user: true,
        utm: { utm_source: "telegram" },
      },
      {
        id: 2,
        user_id: 910000001,
        original_user_id: null,
        channel: "bot",
        evidence: "tagged_link",
        occurred_at: date(2),
        received_at: date(2),
        is_new_user: false,
        utm: {},
      },
      {
        id: 3,
        user_id: null,
        original_user_id: null,
        channel: "web",
        evidence: "tagged_link",
        occurred_at: date(),
        received_at: date(),
        is_new_user: null,
        utm: {},
      },
    ],
    touch_total: 3,
    imports: [],
    candidates: [],
    audit: [{ id: 1, action: "campaign.updated", actor_id: 910000001, created_at: date() }],
    available_codes: Object.fromEntries(
      demoPromos()
        .filter((promo) => !promo.user_id)
        .map((promo) => [String(promo.code), Number(promo.id || promo.promo_code_id)])
    ),
  };
  cards.set(id, value);
  return value;
}

export function advertisingDemoResponse(path: string, options: RequestInit): unknown {
  const url = new URL(path, "https://demo.example.test");
  if (!url.pathname.startsWith("/api/")) url.pathname = `/api${url.pathname}`;
  if (url.pathname === "/api/admin/ads" && (!options.method || options.method === "GET")) {
    let values = demoAds().map((item) => ({
      ...card(Number(item.id)).campaign,
      ...item,
      stats: card(Number(item.id)).campaign.stats,
    }));
    const search = (url.searchParams.get("search") || "").toLowerCase();
    if (search)
      values = values.filter((item) =>
        `${item.source} ${item.start_param}`.toLowerCase().includes(search)
      );
    const page = Number(url.searchParams.get("page") || 0),
      size = Number(url.searchParams.get("page_size") || 10);
    return {
      ok: true,
      campaigns: values.slice(page * size, (page + 1) * size),
      total: values.length,
      page,
      page_size: size,
      totals: { cost: 11700, revenue: 900 },
      revenue_by_currency: { RUB: 900 },
    };
  }
  if (url.pathname.startsWith("/api/advertising/"))
    return { ok: true, captured: false, context: null };
  if (url.pathname === "/api/admin/ads/unassigned")
    return { ok: true, touches: [], total: 0, campaigns: { "101": "QA Advertising" } };
  if (url.pathname === "/api/admin/ads/unassigned/assign") return { ok: true };
  const match = url.pathname.match(
    /^\/api\/admin\/ads\/(\d+)\/(detail|edit|archive|links|bindings|spend|imports|candidates|export)(?:\/.*)?$/
  );
  if (!match) return undefined;
  const value = card(Number(match[1]));
  if (match[2] === "detail") return { ok: true, ...structuredClone(value) };
  if (match[2] === "export") return "currency,product_minor,refund_minor\r\nRUB,160000,70000\r\n";
  const body: Record<string, unknown> =
    typeof options.body === "string" ? JSON.parse(options.body) : {};
  if (match[2] === "edit") {
    value.name = String(body.name);
    value.description = String(body.description || "");
    value.spend_source = String(body.spend_source);
  }
  if (match[2] === "archive") {
    value.archived_at = date();
    value.campaign.is_active = false;
  }
  if (match[2] === "spend")
    value.spends.unshift({
      id: Date.now(),
      amount_minor: String(Math.round(Number(body.amount) * 100)),
      currency: String(body.currency),
      scale: 2,
      source: "manual",
      occurred_at: String(body.occurred_at),
      note: String(body.note || ""),
    });
  if (match[2] === "links" && url.pathname.endsWith("/toggle")) {
    const ident = Number(url.pathname.split("/").at(-2));
    const link = value.links.find((item) => item.id === ident);
    if (link) link.is_active = body.is_active === true;
    return { ok: true };
  }
  if (match[2] === "links")
    value.links.push({
      ...value.links[0],
      id: Date.now(),
      code: "ad_demo_" + value.links.length,
      label: String(body.label),
      destination: String(body.destination),
    });
  if (match[2] === "bindings" && url.pathname.endsWith("/end")) {
    const id = Number(url.pathname.split("/").at(-2));
    const binding = value.bindings.find((item) => item.id === id);
    if (binding) binding.ends_at = date();
  } else if (match[2] === "bindings")
    value.bindings.unshift({
      id: Date.now(),
      promo_code_id: Number(body.promo_code_id),
      code:
        Object.keys(value.available_codes).find(
          (key) => value.available_codes[key] === Number(body.promo_code_id)
        ) || "QA",
      link_id: body.link_id ? Number(body.link_id) : null,
      purpose: String(body.purpose),
      starts_at: date(),
      ends_at: null,
      version: 1,
      is_active: true,
      activations: 1,
      purchases: 1,
      pending: 0,
      refunded: 0,
      effects: {},
    });
  if (match[2] === "imports" && url.pathname.endsWith("/preview")) {
    const batch = {
      id: crypto.randomUUID().replaceAll("-", ""),
      status: "preview",
      account: String(body.account),
      timezone: String(body.timezone),
      fingerprint: "demo",
      rows: String(body.csv).trim().split(/\r?\n/).length - 1,
      granularity: String(body.granularity),
      created_at: date(),
    };
    value.imports.unshift(batch);
    return {
      ok: true,
      batch,
      preview: [
        {
          advertisement: "QA",
          available_metrics: ["impressions", "clicks", "starts"],
          impressions: 1000,
          clicks: 50,
          starts: 20,
          currency: "RUB",
          cost_minor: "450000",
        },
      ],
    };
  }
  if (match[2] === "imports") {
    const batch = value.imports.find((item) => url.pathname.includes(item.id));
    if (batch) batch.status = url.pathname.endsWith("/revert") ? "reverted" : "confirmed";
  }
  value.audit.unshift({
    id: Date.now(),
    action: "campaign.updated",
    actor_id: 910000001,
    created_at: date(),
  });
  return { ok: true };
}
