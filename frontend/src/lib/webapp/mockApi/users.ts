import { withDemoAvatar, withDemoAvatarDetail, withDemoAvatarTicket } from "../demoAvatars.js";
import { compareNullableDate, stringDate } from "../demoMockRuntime.js";
import {
  DATASET,
  type DemoAdminUser,
  type DemoRecord,
  type DemoTicket,
  type DemoUserDetail,
} from "./dataset";
import { demoSupportTickets } from "./state";

export function userName(user: DemoRecord | null | undefined): string {
  const record = (user || {}) as DemoAdminUser;
  return (
    [record.first_name, record.last_name].filter(Boolean).join(" ").trim() ||
    record.username ||
    record.email ||
    String(record.user_id || "")
  );
}

function demoUserSeed(user: DemoAdminUser | null | undefined): number {
  return Math.abs(Number(user?.user_id || user?.telegram_id || 0)) || 1;
}

function demoFutureIso(user: DemoAdminUser, offsetDays = 30): string {
  const seed = demoUserSeed(user);
  const base = Date.parse(user?.registration_date || "") || Date.UTC(2026, 0, 1);
  return new Date(base + (offsetDays + (seed % 180)) * 86400000).toISOString();
}

export function withDemoAdminUserMetrics(user: DemoAdminUser): DemoAdminUser {
  const seed = demoUserSeed(user);
  const paymentsCount =
    user.payments_count ?? (user.panel_status === "bot_only" ? 0 : Math.max(1, seed % 9));
  const paymentsTotal =
    user.payments_total_amount ?? Number(paymentsCount) * (290 + (seed % 11) * 75);
  const invitedCount = user.invited_users_count ?? (seed % 5 === 0 ? seed % 8 : seed % 3);
  const subscriptionExpiresAt =
    user.subscription_expires_at ??
    user.panel_status_expired_at ??
    (user.panel_status === "active" ? demoFutureIso(user, 45) : null);

  return {
    ...user,
    payments_total_amount: paymentsTotal,
    payments_count: paymentsCount,
    payments_currency: user.payments_currency || "RUB",
    invited_users_count: invitedCount,
    subscription_expires_at: subscriptionExpiresAt,
  };
}

export function withDemoAvatars(users: DemoAdminUser[], size = 96): DemoAdminUser[] {
  return (users || []).map((user) => withDemoAvatar(user, size) as DemoAdminUser);
}

export function demoAdminUserById(userId: unknown): DemoAdminUser | undefined {
  return (DATASET.adminUsers || []).find((user) => Number(user.user_id) === Number(userId));
}

export function demoInviteesForUser(userId: unknown): DemoAdminUser[] {
  return (DATASET.adminUsers || [])
    .filter((user) => Number(user.referred_by_id) === Number(userId))
    .sort((a, b) => stringDate(b.registration_date) - stringDate(a.registration_date));
}

export function withDemoReferralSummary(detail: DemoUserDetail): DemoUserDetail {
  if (!detail || typeof detail !== "object") return detail;
  const decorated = withDemoAvatarDetail(detail) as DemoUserDetail;
  const user = decorated.user || {};
  const inviter = user.referred_by_id ? demoAdminUserById(user.referred_by_id) : null;
  const invitees = demoInviteesForUser(user.user_id);
  return {
    ...decorated,
    referral: {
      ...(decorated.referral || {}),
      inviter: inviter ? (withDemoAvatar(inviter) as DemoAdminUser) : null,
      invitees_total: invitees.length,
    },
  };
}

export function withDemoAvatarTickets(tickets: DemoTicket[], size = 96): DemoTicket[] {
  return (tickets || []).map((ticket) => withDemoAvatarTicket(ticket, size) as DemoTicket);
}

function demoSubscriptions(user: DemoAdminUser): DemoRecord[] {
  const detail = DATASET.adminUserDetails?.[String(user.user_id)] || {};
  const subscriptions = Array.isArray(detail.subscriptions)
    ? (detail.subscriptions as DemoRecord[])
    : [];
  const active = detail.active_subscription;
  if (!active || subscriptions.includes(active)) return subscriptions;
  return [active, ...subscriptions];
}

function isDemoActiveSubscription(subscription: DemoRecord): boolean {
  return (
    subscription.is_active === true &&
    stringDate(subscription.end_date as string | null | undefined) > Date.now()
  );
}

function demoSubscriptionSegment(user: DemoAdminUser): "paid" | "trial" | "free" | null {
  let hasPaid = false;
  let hasTrial = false;
  let hasFree = false;
  for (const subscription of demoSubscriptions(user).filter(isDemoActiveSubscription)) {
    const provider = String(subscription.provider || "").toLowerCase();
    const panelStatus = String(subscription.status_from_panel || "").toUpperCase();
    if (provider === "trial" || panelStatus === "TRIAL") hasTrial = true;
    else if (provider) hasPaid = true;
    else hasFree = true;
  }
  if (hasPaid) return "paid";
  if (hasTrial) return "trial";
  if (hasFree) return "free";
  return null;
}

function hasDemoExpiredSubscription(user: DemoAdminUser): boolean {
  return demoSubscriptions(user).some((subscription) => {
    const panelStatus = String(subscription.status_from_panel || "").toLowerCase();
    const hasBlankStatus = !subscription.status_from_panel;
    const hasExpiredEndDate =
      Boolean(subscription.end_date) &&
      stringDate(subscription.end_date as string | null | undefined) <= Date.now();
    return (
      panelStatus === "expired" ||
      (hasBlankStatus && subscription.is_active === false) ||
      hasExpiredEndDate
    );
  });
}

export function filterDemoUsers(params: URLSearchParams): DemoAdminUser[] {
  let out = (DATASET.adminUsers || []).map(withDemoAdminUserMetrics);
  const q = (params.get("q") || params.get("search") || "").trim().toLowerCase();
  if (q) {
    out = out.filter((user) =>
      [
        user.user_id,
        user.telegram_id,
        user.username,
        user.first_name,
        user.last_name,
        user.email,
        user.panel_user_uuid,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(q))
    );
  }

  const filter = params.get("filter") || "all";
  if (filter === "active") out = out.filter((user) => !user.is_banned);
  else if (filter === "banned") out = out.filter((user) => user.is_banned);
  else if (filter === "active_today") {
    const now = new Date();
    const todayStart = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    out = out.filter((user) => stringDate(user.registration_date) >= todayStart);
  } else if (filter === "referred") out = out.filter((user) => user.referred_by_id != null);
  else if (filter === "active_subscription") {
    out = out.filter((user) => demoSubscriptions(user).some(isDemoActiveSubscription));
  } else if (filter === "inactive_subscription") {
    out = out.filter((user) => !demoSubscriptions(user).some(isDemoActiveSubscription));
  } else if (filter === "expired_subscription") {
    out = out.filter(
      (user) =>
        hasDemoExpiredSubscription(user) && !demoSubscriptions(user).some(isDemoActiveSubscription)
    );
  } else if (filter === "paid" || filter === "trial" || filter === "free") {
    out = out.filter((user) => demoSubscriptionSegment(user) === filter);
  } else if (filter === "tg_linked") out = out.filter((user) => user.telegram_linked);
  else if (filter === "no_tg") out = out.filter((user) => !user.telegram_linked);
  else if (filter === "email_linked") out = out.filter((user) => Boolean(user.email));
  else if (filter === "no_email") out = out.filter((user) => !user.email);
  else if (filter === "panel_linked") out = out.filter((user) => Boolean(user.panel_user_uuid));

  const panelStatus = params.get("panel_status") || "all";
  if (panelStatus !== "all") out = out.filter((user) => user.panel_status === panelStatus);

  const premiumTraffic = params.get("premium_traffic") || "all";
  if (premiumTraffic !== "all") {
    out = out.filter((user) => (user.premium_traffic?.state || "none") === premiumTraffic);
  }

  const sort = params.get("sort") || "registered_desc";
  out.sort((a, b) => {
    if (sort === "registered_asc")
      return stringDate(a.registration_date) - stringDate(b.registration_date);
    if (sort === "name_asc") return userName(a).localeCompare(userName(b));
    if (sort === "name_desc") return userName(b).localeCompare(userName(a));
    if (sort === "id_asc") return Number(a.user_id || 0) - Number(b.user_id || 0);
    if (sort === "id_desc") return Number(b.user_id || 0) - Number(a.user_id || 0);
    if (sort === "premium_ratio_asc")
      return Number(a.premium_traffic?.percent ?? -1) - Number(b.premium_traffic?.percent ?? -1);
    if (sort === "premium_ratio_desc")
      return Number(b.premium_traffic?.percent ?? -1) - Number(a.premium_traffic?.percent ?? -1);
    if (sort === "payments_total_asc")
      return Number(a.payments_total_amount || 0) - Number(b.payments_total_amount || 0);
    if (sort === "payments_total_desc")
      return Number(b.payments_total_amount || 0) - Number(a.payments_total_amount || 0);
    if (sort === "payments_count_asc")
      return Number(a.payments_count || 0) - Number(b.payments_count || 0);
    if (sort === "payments_count_desc")
      return Number(b.payments_count || 0) - Number(a.payments_count || 0);
    if (sort === "invited_users_count_asc")
      return Number(a.invited_users_count || 0) - Number(b.invited_users_count || 0);
    if (sort === "invited_users_count_desc")
      return Number(b.invited_users_count || 0) - Number(a.invited_users_count || 0);
    if (sort === "subscription_expires_at_asc")
      return compareNullableDate(a.subscription_expires_at, b.subscription_expires_at, "asc");
    if (sort === "subscription_expires_at_desc")
      return compareNullableDate(a.subscription_expires_at, b.subscription_expires_at, "desc");
    return stringDate(b.registration_date) - stringDate(a.registration_date);
  });

  return out;
}

export function demoSupportCounts(items: DemoTicket[] = demoSupportTickets()): DemoRecord {
  const byStatus: Record<string, number> = {
    open: 0,
    awaiting_admin: 0,
    awaiting_user: 0,
    resolved: 0,
    closed: 0,
  };
  for (const item of items)
    byStatus[String(item.status)] = (byStatus[String(item.status)] || 0) + 1;
  const closed = (byStatus.closed || 0) + (byStatus.resolved || 0);
  return {
    ...byStatus,
    active: items.length - closed,
    closed,
    total: items.length,
    total_unread_admin: items.reduce((sum, item) => sum + Number(item.unread_admin_count || 0), 0),
  };
}

export function filterDemoSupportTickets(
  items: DemoTicket[],
  params: URLSearchParams
): DemoTicket[] {
  let out = [...items];
  const status = params.get("status");
  if (status === "active")
    out = out.filter((item) => !["closed", "resolved"].includes(String(item.status)));
  else if (status === "closed")
    out = out.filter((item) => ["closed", "resolved"].includes(String(item.status)));
  else if (status) out = out.filter((item) => item.status === status);

  const priority = params.get("priority");
  if (priority) out = out.filter((item) => item.priority === priority);
  const category = params.get("category");
  if (category) out = out.filter((item) => item.category === category);
  const search = (params.get("search") || "").trim().toLowerCase();
  if (search) {
    out = out.filter((item) =>
      [item.subject, item.user?.username, item.user?.email, item.ticket_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(search))
    );
  }

  const priorityRank: Record<string, number> = { urgent: 4, high: 3, normal: 2, low: 1 };
  const sort = params.get("sort") || "updated_desc";
  out.sort((a, b) => {
    if (sort === "importance_desc") {
      return (
        (priorityRank[String(b.priority)] || 0) - (priorityRank[String(a.priority)] || 0) ||
        stringDate(b.last_message_at || b.created_at) -
          stringDate(a.last_message_at || a.created_at)
      );
    }
    if (sort === "updated_asc") {
      return (
        stringDate(a.last_message_at || a.created_at) -
        stringDate(b.last_message_at || b.created_at)
      );
    }
    if (sort === "created_desc") return stringDate(b.created_at) - stringDate(a.created_at);
    if (sort === "created_asc") return stringDate(a.created_at) - stringDate(b.created_at);
    return (
      stringDate(b.last_message_at || b.created_at) - stringDate(a.last_message_at || a.created_at)
    );
  });
  return out;
}

export function userSnapshotForTicket(ticket: DemoTicket): DemoRecord {
  const detail = DATASET.adminUserDetails?.[String(ticket?.user_id)] || {};
  const user = detail.user || ticket?.user || {};
  const sub = detail.active_subscription || {};
  return {
    user_id: user.user_id,
    name: userName(user) || user.username || user.email || String(user.user_id || ""),
    username: user.username || "",
    email: user.email || "",
    tariff: sub.tariff_name || sub.tariff_key || "Demo",
    panel_status: user.panel_status || sub.status_from_panel || "",
    remaining: sub.end_date || "",
    regular_traffic: `${sub.traffic_used_bytes || 0} / ${sub.traffic_limit_bytes || 0}`,
    premium_traffic: `${sub.premium_used_bytes || 0} / ${sub.premium_limit_bytes || 0}`,
  };
}
