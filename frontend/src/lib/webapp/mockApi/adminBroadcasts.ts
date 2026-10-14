import { jsonBody } from "../demoMockRuntime.js";
import { type CloneFn, type DemoRecord } from "./dataset";
import { demoBroadcastFailures } from "./broadcastFailures";
import { demoBroadcasts, setDemoBroadcasts } from "./state";
import { issueReviewEnabled } from "./issueReview";
import { SHORTCODE_TOKEN_RE } from "$lib/richtext/telegramHtml";

const DEMO_SHORTCODE_META: [string, string, string][] = [
  ["first_name", "db", "First name"],
  ["last_name", "db", "Last name"],
  ["username", "db", "@username"],
  ["user_id", "db", "User ID"],
  ["email", "db", "User email"],
  ["end_date", "db", "Subscription end date"],
  ["days_left", "db", "Days until expiry"],
  ["subscription_status", "db", "Subscription status"],
  ["tariff_name", "db", "Tariff name"],
  ["tariff_price", "db", "Tariff price"],
  ["traffic_used", "db", "Traffic used, GB"],
  ["traffic_limit", "db", "Traffic limit, GB"],
  ["traffic_left", "db", "Traffic left, GB"],
  ["install_link", "db", "Connection guide link"],
  ["miniapp_link", "db", "Mini App link"],
  ["config_link", "panel", "Subscription key link"],
  ["referral_code", "db", "Referral code"],
  ["referral_bot_link", "db", "Referral link (bot)"],
  ["referral_webapp_link", "db", "Referral link (Mini App)"],
];

const DEMO_SHORTCODE_VALUES: Record<string, string> = {
  first_name: "Alex",
  last_name: "Petrov",
  username: "@alex",
  user_id: "100245",
  email: "alex@example.com",
  end_date: "2030-05-01",
  days_left: "42",
  subscription_status: "active",
  tariff_name: "Premium",
  tariff_price: "299 RUB",
  traffic_used: "30",
  traffic_limit: "100",
  traffic_left: "70",
  install_link: "https://app.example/s/demo",
  miniapp_link: "https://app.example/",
  config_link: "happ://crypt4/demo",
  referral_code: "AB12CD",
  referral_bot_link: "https://t.me/demo_bot?start=ref_uAB12CD",
  referral_webapp_link: "https://app.example/?ref=uAB12CD",
  "sample-tools.plan_label": "Additional services",
};

function demoBroadcastShortcodes(): { shortcodes: DemoRecord[]; allowed_tags: string[] } {
  return {
    shortcodes: [
      ...DEMO_SHORTCODE_META.map(([name, cost, description]) => ({
        name,
        cost,
        description,
      })),
      ...(issueReviewEnabled()
        ? [
            {
              name: "sample-tools.plan_label",
              cost: "db",
              description: "Additional services plan",
              owner: "sample-tools",
            },
          ]
        : []),
    ],
    allowed_tags: ["b", "i", "u", "s", "code", "a", "pre", "blockquote"],
  };
}

function renderDemoShortcodes(text: string): { text: string; unknown: string[] } {
  const unknown = new Set<string>();
  const rendered = text.replace(SHORTCODE_TOKEN_RE, (whole, name: string) => {
    if (name in DEMO_SHORTCODE_VALUES) return DEMO_SHORTCODE_VALUES[name];
    unknown.add(name);
    return whole;
  });
  return { text: rendered, unknown: [...unknown] };
}

type AdminBroadcastRequest = {
  cleanPath: string;
  method: string;
  options: RequestInit;
  params: URLSearchParams;
  clone: CloneFn;
};

export function adminBroadcastDemoResponse({
  cleanPath,
  method,
  options,
  params,
  clone,
}: AdminBroadcastRequest): unknown | undefined {
  if (cleanPath === "/admin/broadcast/audience-counts") {
    return {
      ok: true,
      counts: { all: 1280, active: 742, inactive: 538, expired: 311, never: 227, admins: 2 },
      email_enabled: true,
    };
  }
  if (cleanPath === "/admin/broadcast" && method === "POST") {
    const body = jsonBody(options);
    const channels = Array.isArray(body.channels) ? body.channels : ["telegram"];
    const target = String(body.target || "all");
    const queued = channels.includes("telegram") ? (target === "admins" ? 2 : 1280) : 0;
    const emailQueued = channels.includes("email") ? (target === "admins" ? 1 : 486) : 0;
    const scheduledAt = body.scheduled_at ? new Date(String(body.scheduled_at)) : new Date();
    const scheduled = scheduledAt.getTime() > Date.now();
    const existing = demoBroadcasts();
    const broadcastId =
      Math.max(100, ...existing.map((item) => Number(item.broadcast_id) || 0)) + 1;
    const now = new Date().toISOString();
    const broadcast: DemoRecord = {
      broadcast_id: broadcastId,
      status: scheduled ? "scheduled" : "running",
      target,
      channels,
      texts:
        body.texts && typeof body.texts === "object" ? body.texts : { ru: String(body.text || "") },
      email_subjects:
        body.email_subjects && typeof body.email_subjects === "object"
          ? body.email_subjects
          : body.email_subject
            ? { ru: String(body.email_subject) }
            : {},
      buttons: Array.isArray(body.buttons) ? body.buttons : [],
      scheduled_at: scheduledAt.toISOString(),
      created_at: now,
      started_at: scheduled ? null : now,
      finished_at: null,
      updated_at: now,
      recipient_count: scheduled ? 0 : target === "admins" ? 2 : 1280,
      total_deliveries: scheduled ? 0 : queued + emailQueued,
      successful_deliveries: 0,
      failed_deliveries: 0,
      telegram_sent: 0,
      telegram_failed: 0,
      email_sent: 0,
      email_failed: 0,
      last_error: null,
    };
    if (!target.startsWith("user:")) setDemoBroadcasts([broadcast, ...existing]);
    return {
      ok: true,
      queued,
      failed: 0,
      email_queued: emailQueued,
      target,
      channels,
      broadcast,
    };
  }
  if (cleanPath === "/admin/broadcasts" && method === "GET") {
    const next = demoBroadcasts().map((item) => {
      if (item.status !== "running") return item;
      const total = Number(item.total_deliveries || 0);
      const sent = Math.min(total, Number(item.successful_deliveries || 0) + 117);
      const telegramSent =
        Array.isArray(item.channels) && item.channels.includes("telegram")
          ? Math.min(total, Number(item.telegram_sent || 0) + 91)
          : 0;
      const emailSent = Math.max(0, sent - telegramSent - Number(item.failed_deliveries || 0));
      const completed = total > 0 && sent + Number(item.failed_deliveries || 0) >= total;
      return {
        ...item,
        status: completed ? "completed_with_errors" : "running",
        successful_deliveries: sent,
        telegram_sent: telegramSent,
        email_sent: emailSent,
        updated_at: new Date().toISOString(),
        finished_at: completed ? new Date().toISOString() : null,
      };
    });
    setDemoBroadcasts(next);
    return { ok: true, broadcasts: clone(next) };
  }
  const broadcastFailuresMatch = cleanPath.match(/^\/admin\/broadcasts\/(\d+)\/failures$/);
  if (broadcastFailuresMatch && method === "GET") {
    return demoBroadcastFailures(Number(broadcastFailuresMatch[1]), params);
  }
  const broadcastItemMatch = cleanPath.match(/^\/admin\/broadcasts\/(\d+)$/);
  if (broadcastItemMatch && method === "DELETE") {
    const broadcastId = Number(broadcastItemMatch[1]);
    setDemoBroadcasts(demoBroadcasts().filter((item) => Number(item.broadcast_id) !== broadcastId));
    return { ok: true, deleted: true, broadcast_id: broadcastId };
  }
  if (broadcastItemMatch && method === "PATCH") {
    const broadcastId = Number(broadcastItemMatch[1]);
    const body = jsonBody(options);
    const scheduledAt = new Date(String(body.scheduled_at || ""));
    const next = demoBroadcasts().map((item) =>
      Number(item.broadcast_id) === broadcastId
        ? {
            ...item,
            status: "scheduled",
            scheduled_at: scheduledAt.toISOString(),
            updated_at: new Date().toISOString(),
          }
        : item
    );
    setDemoBroadcasts(next);
    return {
      ok: true,
      ...clone(next.find((item) => Number(item.broadcast_id) === broadcastId) || {}),
    };
  }
  if (cleanPath === "/admin/broadcast/shortcodes") {
    return { ok: true, ...demoBroadcastShortcodes() };
  }
  if (cleanPath === "/admin/broadcast/preview" && method === "POST") {
    const body = jsonBody(options);
    const rendered = renderDemoShortcodes(String(body.text || ""));
    const subjectRaw = String(body.email_subject || "");
    return {
      ok: true,
      rendered_text: rendered.text,
      rendered_subject: subjectRaw ? renderDemoShortcodes(subjectRaw).text : null,
      unknown_shortcodes: rendered.unknown,
      length: rendered.text.length,
      sent: String(body.mode || "render") === "send_telegram",
    };
  }
  return undefined;
}
