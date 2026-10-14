import en from "../../../../../locales/en.json";
import ru from "../../../../../locales/ru.json";
import { DATASET, defaultClone, type DemoRecord } from "./dataset.js";
import { jsonBody } from "../demoMockRuntime.js";
import { filterDemoUsers } from "./users.js";
import { adminDemoBalance } from "./balance.js";
import type { components } from "../../api/openapi.generated.js";

let reviewSourceRemoved = false;
let reviewSourceRestricted = false;
let reviewMergedTarget: number | null = null;
const REVIEW_SOURCE_ID = -987654;
const REVIEW_PROMO_ID = Number(DATASET.promos?.[0]?.id);

/** Both accounts redeemed the same code before merging; its two grants stay unchanged. */
function sharedPromoActivations(): components["schemas"]["PromoActivationOut"][] {
  const target = Object.values(DATASET.adminUserDetails || {}).find(
    (detail) => detail.user?.minishop_id === "ms_100000000000400080000000000de418"
  )?.user;
  return [REVIEW_SOURCE_ID, Number(target?.user_id)].map((userId, index) => ({
    activation_id: 970001 + index,
    promo_id: REVIEW_PROMO_ID,
    user_id: reviewMergedTarget ?? userId,
    user_label:
      reviewMergedTarget !== null || index === 1 ? String(target?.first_name || "") : "Alex",
    user_minishop_id:
      reviewMergedTarget !== null || index === 1
        ? target?.minishop_id || null
        : "ms_1234567890abcdef1234567890abcdef",
    telegram_id: null,
    activated_at: index === 0 ? "2030-04-12T12:00:00Z" : "2030-04-10T12:00:00Z",
    bonus_days: 7,
    granted_days: 7,
    granted_gb: null,
    granted_regular_traffic_gb: null,
    granted_premium_traffic_gb: null,
    regular_traffic_gb: null,
    premium_traffic_gb: null,
    charged_days: null,
    charged_gb: null,
    charged_months: null,
    base_amount: null,
    discount_amount: null,
    discount_percent: null,
    duration_multiplier: null,
    traffic_multiplier: null,
    effect_summary: null,
    applies_to: "subscription",
    payment_id: null,
    payment_amount: null,
    payment_currency: null,
    payment_created_at: null,
    payment_description: null,
    payment_provider: null,
    payment_sale_mode: null,
    payment_status: null,
  }));
}
function reviewSource() {
  const base = defaultClone(Object.values(DATASET.adminUserDetails || {})[0] || {});
  return {
    ...base,
    ok: true,
    user: {
      ...base.user,
      user_id: REVIEW_SOURCE_ID,
      minishop_id: "ms_1234567890abcdef1234567890abcdef",
      first_name: "Alex",
      last_name: "Duplicate account",
      email: "alex.duplicate@example.com",
      username: null,
      telegram_id: null,
      is_admin: false,
      is_banned: false,
    },
    active_subscription: base.active_subscription
      ? { ...base.active_subscription, tariff_name: "Standard", end_date: "2031-04-12T12:00:00Z" }
      : null,
    balance: {
      ...adminDemoBalance(REVIEW_SOURCE_ID),
      enabled: true,
      amount: "125.00",
      amount_minor: 12500,
    },
  };
}

export function issueReviewEnabled() {
  return new URLSearchParams(window.location.search).get("issues_demo") === "1";
}

export function issueReviewDemoResponse(
  path: string,
  options: RequestInit,
  language: string
): unknown {
  const fullPath = path;
  path = path.split("?")[0];
  if (path === "/admin/message/targets") {
    return {
      ok: true,
      sections: issueReviewEnabled()
        ? [
            {
              id: "/extensions/sample-tools/services",
              label: (language === "ru" ? ru : en).admin_demo_plugin_page,
              owner: "sample-tools",
            },
          ]
        : [],
    };
  }
  if (!issueReviewEnabled()) return undefined;
  const promoMatch = path.match(/^\/admin\/promos\/(\d+)\/activations$/);
  if (
    promoMatch &&
    Number(promoMatch[1]) === REVIEW_PROMO_ID &&
    new URLSearchParams(window.location.search).get("merge_demo") === "shared-promo"
  ) {
    const params = new URLSearchParams(fullPath.split("?")[1] || "");
    const page = Math.max(0, Number(params.get("page")) || 0);
    const pageSize = Math.max(1, Math.min(100, Number(params.get("page_size")) || 25));
    const activations = sharedPromoActivations();
    return {
      ok: true,
      activations: activations.slice(page * pageSize, (page + 1) * pageSize),
      total: activations.length,
      page,
      page_size: pageSize,
      revenue_summary: { payments_total: 0, revenue_payments: 0, currencies: [] },
    };
  }
  const extraSources = [
    reviewSource(),
    ...Array.from({ length: 28 }, (_, index) => ({
      ...reviewSource(),
      user: {
        ...reviewSource().user,
        user_id: -987653 + index,
        minishop_id: `ms_${(index + 100).toString(16).padStart(32, "0")}`,
        first_name: "Review",
        last_name: `Candidate ${index + 1}`,
        email: `review.${index + 1}@example.com`,
        is_banned: index === 1,
      },
    })),
  ];
  if (path === "/admin/users") {
    const params = new URLSearchParams(fullPath.split("?")[1] || "");
    const query = (params.get("q") || "").trim().replace(/^@/, "").toLowerCase();
    params.set("q", query);
    const users = [
      ...(!reviewSourceRemoved ? extraSources : extraSources.slice(1)).map((detail) => detail.user),
      ...filterDemoUsers(params),
    ].filter(
      (user) =>
        !query ||
        [
          user.user_id,
          user.telegram_id,
          user.username,
          user.email,
          user.first_name,
          user.last_name,
          `${user.first_name || ""} ${user.last_name || ""}`,
          user.minishop_id,
          "panel_username" in user ? user.panel_username : null,
          user.panel_user_uuid,
          "account_id" in user ? user.account_id : null,
        ].some((value) =>
          String(value || "")
            .toLowerCase()
            .includes(query)
        )
    );
    const page = Math.max(0, Number(params.get("page")) || 0);
    const pageSize = Math.max(1, Math.min(100, Number(params.get("page_size")) || 25));
    return {
      ok: true,
      users: users.slice(page * pageSize, (page + 1) * pageSize),
      total: users.length,
      page,
      page_size: pageSize,
    };
  }
  const detailMatch = path.match(/^\/admin\/users\/(-?\d+)$/);
  if (detailMatch) {
    const detail = extraSources.find((item) => item.user.user_id === Number(detailMatch[1]));
    if (detail)
      return (reviewSourceRemoved && detail.user.user_id === REVIEW_SOURCE_ID) ||
        detail.user.user_id === -987651
        ? { ok: false, error: "not_found" }
        : detail;
  }
  const contextMatch = path.match(/^\/admin\/users\/(-?\d+)\/merge-context$/);
  if (contextMatch) {
    const id = Number(contextMatch[1]);
    const detail =
      extraSources.find((item) => item.user.user_id === id) ||
      DATASET.adminUserDetails?.[String(id)];
    if (!detail || (id === REVIEW_SOURCE_ID && reviewSourceRemoved) || id === -987651)
      return { ok: false, error: "not_found" };
    const reason = detail.user?.is_banned
      ? "account_merge_banned"
      : id === -987653 || (id === REVIEW_SOURCE_ID && reviewSourceRestricted)
        ? "account_merge_privileged_source"
        : null;
    return {
      ok: true,
      user_id: id,
      auth_identities:
        id === REVIEW_SOURCE_ID
          ? [
              {
                provider: "google",
                email: "alex.duplicate@example.com",
                email_verified: true,
                display_name: "Alex",
              },
            ]
          : id === -987650
            ? [
                {
                  provider: "yandex",
                  email: "review.4@example.com",
                  email_verified: true,
                  display_name: "Review",
                },
              ]
            : id > 0
              ? [
                  {
                    provider: "yandex",
                    email: detail.user?.email || null,
                    email_verified: true,
                    display_name: null,
                  },
                ]
              : [],
      verified_emails: [detail.user?.email].filter(Boolean),
      passkey_count: id === REVIEW_SOURCE_ID ? 1 : 0,
      password_available: true,
      merge_eligibility: { allowed: !reason, reason },
    };
  }
  const match = path.match(/^\/admin\/users\/(-?\d+)\/merge$/);
  if (!match || String(options.method).toUpperCase() !== "POST") return undefined;
  const body = jsonBody(options);
  const targetId = Number(match[1]);
  const sourceId = Number(body.source_user_id);
  if (Number(body.confirmation_user_id) !== targetId)
    return { ok: false, error: "account_merge_confirmation_required" };
  if (sourceId === targetId) return { ok: false, error: "account_merge_not_required" };
  const target = DATASET.adminUserDetails?.[String(targetId)];
  const source =
    sourceId === REVIEW_SOURCE_ID && !reviewSourceRemoved
      ? reviewSource()
      : extraSources.find((detail) => detail.user.user_id === sourceId) ||
        DATASET.adminUserDetails?.[String(sourceId)];
  if (!target || !source) return { ok: false, error: "not_found" };
  if (new URLSearchParams(window.location.search).get("merge_demo") === "changed") {
    reviewSourceRestricted = true;
    return { ok: false, error: "account_merge_privileged_source" };
  }
  if (target.user?.is_admin || source.user?.is_admin)
    return { ok: false, error: "account_merge_privileged_source" };
  if (
    target.user?.telegram_id &&
    source.user?.telegram_id &&
    target.user.telegram_id !== source.user.telegram_id
  )
    return { ok: false, error: "account_merge_telegram_conflict" };
  if (sourceId === REVIEW_SOURCE_ID) {
    reviewSourceRemoved = true;
    reviewMergedTarget = targetId;
  }
  return {
    ok: true,
    user_id: targetId,
    source_user_id: sourceId,
    panel_reconciliation_pending: false,
    final_end_date: target.active_subscription?.end_date || null,
  };
}

/** A local review fixture exercises both grouped and distinct referral conditions. */
export function issueReviewReferral(referral: DemoRecord, language = "ru") {
  if (!issueReviewEnabled()) return referral;
  const locale = language === "ru" ? ru : en;
  const oneMonth = `1 ${locale.wa_sub_term_month_one}`;
  const details = [
    { id: "shared-1", months: 1, title: oneMonth, inviter_days: 5, friend_days: 3 },
    {
      id: "shared-3",
      months: 3,
      title: `3 ${locale.wa_sub_term_month_few}`,
      inviter_days: 15,
      friend_days: 9,
    },
  ];
  return {
    ...defaultClone(referral),
    bonus_details: [
      {
        id: "standard",
        type: "tariff_summary",
        tariff_key: "standard",
        tariff_keys: ["standard", "premium"],
        tariff_names: ["Standard", "Premium"],
        title: "Standard, Premium",
        inviter_min_days: 5,
        inviter_max_days: 15,
        friend_min_days: 3,
        friend_max_days: 9,
        details,
      },
      {
        id: "family",
        type: "tariff_summary",
        tariff_key: "family",
        tariff_keys: ["family"],
        tariff_names: ["Family"],
        title: "Family",
        inviter_min_days: 10,
        inviter_max_days: 10,
        friend_min_days: 7,
        friend_max_days: 7,
        details: [{ id: "family-1", months: 1, title: oneMonth, inviter_days: 10, friend_days: 7 }],
      },
    ],
  };
}
