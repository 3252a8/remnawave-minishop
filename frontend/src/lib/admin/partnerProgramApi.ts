import type { AdminApi } from "../../admin/adminStores.js";
import type {
  ApplicationRow,
  PartnerAuditRow,
  PartnerChartPoint,
  PartnerClientRow,
  PartnerCommissionRow,
  PartnerLedgerRow,
  PartnerRow,
  WithdrawalRow,
} from "./previewMock/partnerProgram.js";

type JsonRecord = Record<string, unknown>;

export type PartnerLinkRow = { id: "telegram" | "web"; labelKey: string; url: string };
export const PARTNER_LIST_PAGE_SIZE = 25;

export type AdminPartnerListQuery = {
  page: number;
  search: string;
  status: string;
  sort: string;
  limit?: number;
};

export const DEFAULT_PARTNER_LIST_QUERY: AdminPartnerListQuery = {
  page: 0,
  search: "",
  status: "all",
  sort: "clients_desc",
};

export type AdminPartnerDashboard = {
  active: number;
  paused: number;
  clients: number;
  gross: number;
  commissions: number;
  paid: number;
  available: number;
  requested: number;
  hold: number;
  revenue: PartnerChartPoint[];
  payouts: PartnerChartPoint[];
};

export type AdminPartnerDetail = {
  partner: PartnerRow;
  links: PartnerLinkRow[];
  clients: PartnerClientRow[];
  commissions: PartnerCommissionRow[];
  withdrawals: WithdrawalRow[];
  ledger: PartnerLedgerRow[];
  audit: PartnerAuditRow[];
};

function record(value: unknown): JsonRecord {
  return value && typeof value === "object" ? (value as JsonRecord) : {};
}

export function requirePartnerAdminResponse(value: unknown): JsonRecord {
  const payload = record(value);
  if (payload.ok === false) {
    throw new Error(String(payload.message || payload.error || "partner_action_failed"));
  }
  return payload;
}

function records(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.map(record) : [];
}

function number(value: unknown): number {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function major(value: unknown, scale: unknown): number {
  return number(value) / 10 ** Math.max(0, number(scale));
}

function source(value: unknown): PartnerClientRow["source"] {
  if (value === "partner_telegram_link") return "telegram";
  if (value === "partner_web_link") return "web";
  return "import";
}

function balanceFor(profile: JsonRecord, currency: string): JsonRecord {
  return (
    records(profile.balances).find(
      (item) => String(item.currency || "").toUpperCase() === currency.toUpperCase()
    ) || {}
  );
}

export function mapPartner(profile: JsonRecord, currency: string): PartnerRow {
  const balance = balanceFor(profile, currency);
  const scale = number(balance.currency_scale || 2);
  const userId = number(profile.user_id);
  return {
    id: String(profile.partner_id || ""),
    userId,
    name: String(profile.display_label || `#${userId}`),
    handle: profile.username
      ? `@${String(profile.username).replace(/^@/, "")}`
      : userId
        ? `#${userId}`
        : "—",
    avatarUrl: String(profile.avatar_url || ""),
    status: String(profile.status || "closed") as PartnerRow["status"],
    rate: number(profile.commission_bps) / 100,
    clients: number(profile.clients_count),
    payments: number(profile.payments_count),
    gross: major(profile.gross_minor, scale),
    earned: major(profile.earned_minor, scale),
    available: major(balance.available_minor, scale),
    currencyScale: scale,
    activated: String(profile.activated_at || profile.created_at || ""),
  };
}

export function mapApplication(item: JsonRecord): ApplicationRow {
  const userId = number(item.user_id);
  return {
    id: String(item.application_id || ""),
    userId,
    user: String(item.display_label || `#${userId}`),
    handle: item.username
      ? `@${String(item.username).replace(/^@/, "")}`
      : userId
        ? `#${userId}`
        : "—",
    avatarUrl: String(item.avatar_url || ""),
    submitted: String(item.submitted_at || ""),
    status: String(item.status || "canceled") as ApplicationRow["status"],
    messageKey: String(item.message || ""),
  };
}

export function mapWithdrawal(
  item: JsonRecord,
  partnerById: Map<string, PartnerRow>
): WithdrawalRow {
  const partnerId = String(item.partner_id || "");
  const partner = partnerById.get(partnerId);
  const userId = number(item.user_id) || partner?.userId || 0;
  return {
    id: String(item.withdrawal_id || ""),
    partnerId,
    partner: String(item.display_label || partner?.name || `#${partnerId}`),
    handle: item.username
      ? `@${String(item.username).replace(/^@/, "")}`
      : partner?.handle || (userId ? `#${userId}` : `#${partnerId}`),
    avatarUrl: String(item.avatar_url || partner?.avatarUrl || ""),
    method: String(item.method_type || "bank_card") as WithdrawalRow["method"],
    masked: String(item.masked_requisites || ""),
    amount: major(item.amount_minor, item.currency_scale),
    status: String(item.status || "failed") as WithdrawalRow["status"],
    requested: String(item.requested_at || ""),
    processedAt: String(item.paid_at || item.decided_at || item.processing_at || ""),
    noteKey: String(item.status_message || ""),
    statusVersion: number(item.status_version),
    externalReference: String(item.external_reference || ""),
    settlementAmount: String(item.settlement_amount || ""),
  };
}

export async function loadPartnerDashboard(
  api: AdminApi,
  currency: string
): Promise<AdminPartnerDashboard> {
  const payload = record(
    await api(`/admin/partners/overview?currency=${encodeURIComponent(currency)}&days=all`)
  );
  const metrics = record(payload.metrics);
  const scale = number(payload.currency_scale || 2);
  const series = records(payload.series);
  return {
    active: number(metrics.active_partners),
    paused: number(metrics.paused_partners),
    clients: number(metrics.clients),
    gross: major(metrics.gross_minor, scale),
    commissions: major(metrics.commissions_minor, scale),
    paid: major(metrics.paid_minor, scale),
    available: major(metrics.available_minor, scale),
    requested: major(metrics.requested_minor, scale),
    hold: major(metrics.pending_minor, scale),
    revenue: series.map((item) => ({
      date: String(item.date || ""),
      amount: major(item.gross_minor, scale),
    })),
    payouts: series.map((item) => ({
      date: String(item.date || ""),
      amount: major(item.paid_minor, scale),
    })),
  };
}

export async function loadPartnerLists(
  api: AdminApi,
  currency: string,
  query: AdminPartnerListQuery = DEFAULT_PARTNER_LIST_QUERY
): Promise<{
  partners: PartnerRow[];
  partnerTotal: number;
  applications: ApplicationRow[];
  withdrawals: WithdrawalRow[];
}> {
  const [partnerPage, applicationsPayload, withdrawalPayload] = await Promise.all([
    loadPartnerPage(api, currency, query),
    api("/admin/partner-applications?limit=200"),
    api(`/admin/partner-withdrawals?currency=${encodeURIComponent(currency)}&limit=200`),
  ]);
  const partnerMap = new Map(partnerPage.partners.map((partner) => [partner.id, partner]));
  return {
    partners: partnerPage.partners,
    partnerTotal: partnerPage.total,
    applications: records(record(applicationsPayload).applications).map(mapApplication),
    withdrawals: records(record(withdrawalPayload).withdrawals).map((item) =>
      mapWithdrawal(item, partnerMap)
    ),
  };
}

export async function loadPartnerPage(
  api: AdminApi,
  currency: string,
  query: AdminPartnerListQuery
): Promise<{ partners: PartnerRow[]; total: number }> {
  const pageSize = Math.min(
    PARTNER_LIST_PAGE_SIZE,
    Math.max(1, Number(query.limit) || PARTNER_LIST_PAGE_SIZE)
  );
  const partnerQuery = new URLSearchParams({
    currency,
    limit: String(pageSize),
    offset: String(Math.max(0, query.page) * pageSize),
    sort: query.sort || "created_desc",
  });
  if (query.search.trim()) partnerQuery.set("search", query.search.trim());
  if (query.status && query.status !== "all") partnerQuery.set("status", query.status);
  const partnersPayload = await api(`/admin/partners?${partnerQuery.toString()}`);
  const partnerPayload = record(partnersPayload);
  const partners = records(partnerPayload.partners).map((item) => mapPartner(item, currency));
  return {
    partners,
    total: number(partnerPayload.total),
  };
}

export async function loadPartnerDetail(
  api: AdminApi,
  partnerId: string,
  currency: string,
  path: string
): Promise<AdminPartnerDetail> {
  const payload = record(await api(path as never));
  const profile = record(payload.partner);
  const partner = mapPartner(profile, currency);
  const partnerMap = new Map([[partner.id, partner]]);
  const linksRecord = record(profile.links);
  const links: PartnerLinkRow[] = [];
  if (linksRecord.telegram)
    links.push({ id: "telegram", labelKey: "TG", url: String(linksRecord.telegram) });
  if (linksRecord.web) links.push({ id: "web", labelKey: "WEB", url: String(linksRecord.web) });
  return {
    partner,
    links,
    clients: records(payload.clients).map((item) => ({
      id: String(item.public_client_id || ""),
      userId: number(item.client_user_id),
      label: String(item.label || item.public_client_id || ""),
      handle: String(item.public_client_id || "—"),
      attributed: String(item.attributed_at || ""),
      source: source(item.source),
      payments: number(item.payments_count),
      gross: major(item.gross_minor, item.currency_scale),
    })),
    commissions: records(payload.commissions).map((item) => ({
      id: String(item.commission_id || ""),
      paymentId: number(item.payment_id),
      clientUserId: 0,
      client: String(item.client_label || item.client_public_id || ""),
      clientHandle: String(item.client_public_id || ""),
      created: String(item.created_at || ""),
      gross: major(item.gross_amount_minor, item.currency_scale),
      rate: number(item.commission_bps) / 100,
      amount: major(item.commission_amount_minor, item.currency_scale),
      status: String(item.status || "excluded") as PartnerCommissionRow["status"],
    })),
    withdrawals: records(payload.withdrawals).map((item) => mapWithdrawal(item, partnerMap)),
    ledger: records(payload.ledger).map((item) => ({
      id: String(item.ledger_entry_id || ""),
      created: String(item.created_at || ""),
      kindKey: String(item.kind || ""),
      amount: major(item.amount_minor, item.currency_scale),
      balanceAfter: major(item.balance_after_minor, item.currency_scale),
      refId: String(item.internal_reference || ""),
      refKind: "",
    })),
    audit: records(payload.audit).map((item) => ({
      id: String(item.audit_event_id || ""),
      created: String(item.created_at || ""),
      actorUserId: number(item.actor_user_id),
      actor: String(item.actor_type || "system"),
      actionKey: String(item.event_type || ""),
      detail: String(item.reason || ""),
    })),
  };
}
