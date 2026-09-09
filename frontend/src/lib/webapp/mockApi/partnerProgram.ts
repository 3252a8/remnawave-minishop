import { paged, queryParams, stringDate } from "../demoMockRuntime.js";
import { DATASET, type DemoAdminUser, type DemoRecord } from "./dataset.js";

const PARTNER_COUNT = 6;
const CLIENT_COUNT = 48;
const CURRENCY = "RUB";
const CURRENCY_SCALE = 2;
const HOLD_DAYS = 7;
const DAY_MS = 86_400_000;

type PartnerStatus = "active" | "paused" | "closed";
type CommissionStatus = "pending" | "available";
type WithdrawalStatus = "requested" | "processing" | "paid" | "failed";

type PartnerFixture = {
  partnerId: number;
  user: DemoAdminUser;
  status: PartnerStatus;
  commissionBps: number;
  activatedAt: string;
};

type ClientFixture = {
  partnerId: number;
  clientId: number;
  user: DemoAdminUser;
  source: "partner_telegram_link" | "partner_web_link" | "referral_import";
  attributedAt: string;
  payments: DemoRecord[];
};

type CommissionFixture = {
  partnerId: number;
  commissionId: number;
  client: ClientFixture;
  payment: DemoRecord;
  grossMinor: number;
  amountMinor: number;
  status: CommissionStatus;
  sourcePaidAt: string;
  availableAt: string;
};

type WithdrawalFixture = {
  withdrawalId: number;
  partnerId: number;
  methodId: "bank_card" | "sbp" | "crypto";
  amountMinor: number;
  status: WithdrawalStatus;
  masked: string;
  requestedAt: string;
  processingAt: string | null;
  paidAt: string | null;
  decidedAt: string | null;
};

type ApplicationFixture = {
  applicationId: number;
  user: DemoAdminUser;
  status: "pending" | "approved" | "rejected" | "canceled";
  submittedAt: string;
  message: string;
};

type PartnerBalance = {
  availableMinor: number;
  pendingMinor: number;
  reservedMinor: number;
  lifetimeMinor: number;
};

function idOf(user: DemoAdminUser | null | undefined): number {
  return Number(user?.user_id ?? user?.id ?? 0);
}

function paymentId(payment: DemoRecord): number {
  return Number(payment.payment_id || payment.id || 0);
}

function paymentUserId(payment: DemoRecord): number {
  return Number(payment.user_id || 0);
}

function paymentDate(payment: DemoRecord): string {
  return String(payment.updated_at || payment.created_at || "");
}

function iso(value: number | string | null | undefined, fallback: number): string {
  const parsed = typeof value === "number" ? value : stringDate(value);
  return new Date(parsed || fallback).toISOString();
}

function nameOf(user: DemoAdminUser): string {
  const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
  return fullName || String(user.username || `#${idOf(user)}`);
}

function usernameOf(user: DemoAdminUser): string | null {
  const username = String(user.username || "")
    .replace(/^@/, "")
    .trim();
  return username || null;
}

function avatarOf(user: DemoAdminUser): string | null {
  const avatar = String(user.avatar_url || user.telegram_photo_url || "").trim();
  return avatar || null;
}

function amountMinor(payment: DemoRecord): number {
  return Math.max(0, Math.round(Number(payment.amount || 0) * 10 ** CURRENCY_SCALE));
}

function isEligiblePayment(payment: DemoRecord): boolean {
  return (
    String(payment.status || "").toLowerCase() === "succeeded" &&
    String(payment.currency || "").toUpperCase() === CURRENCY &&
    amountMinor(payment) > 0 &&
    paymentId(payment) > 0 &&
    paymentUserId(payment) > 0
  );
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

const users = DATASET.adminUsers || [];
const eligiblePayments = (DATASET.adminPayments || []).filter(isEligiblePayment);
const paymentsByUser = new Map<number, DemoRecord[]>();

for (const payment of eligiblePayments) {
  const userId = paymentUserId(payment);
  const items = paymentsByUser.get(userId) || [];
  items.push(payment);
  paymentsByUser.set(userId, items);
}

for (const items of paymentsByUser.values()) {
  items.sort((left, right) => stringDate(paymentDate(right)) - stringDate(paymentDate(left)));
}

const latestPaymentTime = Math.max(
  Date.UTC(2026, 4, 28),
  ...eligiblePayments.map((payment) => stringDate(paymentDate(payment)))
);
const currentUserId = idOf(DATASET.currentUser);
const partnerCandidates = users
  .filter((user) => paymentsByUser.has(idOf(user)))
  .sort((left, right) => {
    const leftId = idOf(left);
    const rightId = idOf(right);
    if (leftId === currentUserId) return -1;
    if (rightId === currentUserId) return 1;
    const paymentDelta =
      (paymentsByUser.get(rightId)?.length || 0) - (paymentsByUser.get(leftId)?.length || 0);
    return paymentDelta || leftId - rightId;
  })
  .slice(0, PARTNER_COUNT);

const commissionRates = [3000, 2800, 3200, 2500, 3000, 2700];
const partnerFixtures: PartnerFixture[] = partnerCandidates.map((user, index) => ({
  partnerId: 10_001 + index,
  user,
  status: index === 2 ? "paused" : index === 5 ? "closed" : "active",
  commissionBps: commissionRates[index] || 3000,
  activatedAt: iso(user.registration_date, latestPaymentTime - (180 - index * 14) * DAY_MS),
}));
const partnerUserIds = new Set(partnerFixtures.map((partner) => idOf(partner.user)));

const clientCandidates = users
  .filter((user) => !partnerUserIds.has(idOf(user)) && paymentsByUser.has(idOf(user)))
  .sort((left, right) => {
    const leftPayments = paymentsByUser.get(idOf(left)) || [];
    const rightPayments = paymentsByUser.get(idOf(right)) || [];
    const recentDelta =
      stringDate(paymentDate(rightPayments[0] || {})) -
      stringDate(paymentDate(leftPayments[0] || {}));
    return recentDelta || idOf(left) - idOf(right);
  })
  .slice(0, CLIENT_COUNT);

const attributionSources: ClientFixture["source"][] = [
  "partner_telegram_link",
  "partner_web_link",
  "referral_import",
];
const clientFixtures: ClientFixture[] = clientCandidates.map((user, index) => {
  const partner = partnerFixtures[index % partnerFixtures.length];
  const payments = paymentsByUser.get(idOf(user)) || [];
  const firstPaymentTime = Math.min(...payments.map((payment) => stringDate(paymentDate(payment))));
  const registeredAt = stringDate(user.registration_date);
  return {
    partnerId: partner.partnerId,
    clientId: 20_001 + index,
    user,
    source: attributionSources[index % attributionSources.length],
    attributedAt: iso(Math.min(firstPaymentTime - DAY_MS, Math.max(registeredAt, 1)), registeredAt),
    payments,
  };
});

const partnersById = new Map(partnerFixtures.map((partner) => [partner.partnerId, partner]));
const commissionFixtures: CommissionFixture[] = clientFixtures.flatMap((client) => {
  const partner = partnersById.get(client.partnerId);
  if (!partner) return [];
  return client.payments.map((payment) => {
    const grossMinor = amountMinor(payment);
    const sourcePaidTime = stringDate(paymentDate(payment));
    const availableTime = sourcePaidTime + HOLD_DAYS * DAY_MS;
    return {
      partnerId: partner.partnerId,
      commissionId: paymentId(payment),
      client,
      payment,
      grossMinor,
      amountMinor: Math.round((grossMinor * partner.commissionBps) / 10_000),
      status: availableTime > latestPaymentTime ? "pending" : "available",
      sourcePaidAt: iso(sourcePaidTime, latestPaymentTime),
      availableAt: iso(availableTime, latestPaymentTime),
    };
  });
});

function availableCommissionMinor(partnerId: number): number {
  return sum(
    commissionFixtures
      .filter((item) => item.partnerId === partnerId && item.status === "available")
      .map((item) => item.amountMinor)
  );
}

function withdrawalAmount(partnerId: number, share: number): number {
  const available = availableCommissionMinor(partnerId);
  return Math.max(1, Math.floor((available * share) / 100) * 100);
}

const withdrawalFixtures: WithdrawalFixture[] = partnerFixtures.flatMap((partner, index) => {
  const paidAmount = withdrawalAmount(partner.partnerId, index === 0 ? 0.2 : 0.25);
  const requestedAt = latestPaymentTime - (18 + index * 9) * DAY_MS;
  const primary: WithdrawalFixture = {
    withdrawalId: 30_001 + index,
    partnerId: partner.partnerId,
    methodId: index % 3 === 0 ? "bank_card" : index % 3 === 1 ? "crypto" : "sbp",
    amountMinor: paidAmount,
    status: index === 1 ? "processing" : index === 4 ? "failed" : "paid",
    masked: index % 3 === 0 ? "•••• 4242" : index % 3 === 1 ? "TRC20 ••••8Fx2" : "+7 ••• •••-12-34",
    requestedAt: iso(requestedAt, latestPaymentTime),
    processingAt: iso(requestedAt + DAY_MS, latestPaymentTime),
    paidAt: index === 1 || index === 4 ? null : iso(requestedAt + 2 * DAY_MS, latestPaymentTime),
    decidedAt: iso(requestedAt + 2 * DAY_MS, latestPaymentTime),
  };
  if (index !== 0) return [primary];
  return [
    primary,
    {
      withdrawalId: 30_100,
      partnerId: partner.partnerId,
      methodId: "sbp",
      amountMinor: withdrawalAmount(partner.partnerId, 0.1),
      status: "requested",
      masked: "+7 ••• •••-77-05",
      requestedAt: iso(latestPaymentTime - DAY_MS, latestPaymentTime),
      processingAt: null,
      paidAt: null,
      decidedAt: null,
    },
  ];
});

const occupiedUserIds = new Set([
  ...partnerUserIds,
  ...clientFixtures.map((client) => idOf(client.user)),
]);
const applicationMessages = [
  "partners_preview_application_guides",
  "partners_preview_application_community",
  "partners_preview_application_privacy",
  "partners_preview_application_spam",
];
const applicationStatuses: ApplicationFixture["status"][] = [
  "pending",
  "pending",
  "approved",
  "rejected",
];
const applicationFixtures: ApplicationFixture[] = users
  .filter((user) => !occupiedUserIds.has(idOf(user)))
  .sort((left, right) => stringDate(right.registration_date) - stringDate(left.registration_date))
  .slice(0, applicationStatuses.length)
  .map((user, index) => ({
    applicationId: 40_001 + index,
    user,
    status: applicationStatuses[index],
    submittedAt: iso(latestPaymentTime - (index + 1) * 2 * DAY_MS, latestPaymentTime),
    message: applicationMessages[index],
  }));

function balanceFor(partnerId: number): PartnerBalance {
  const commissions = commissionFixtures.filter((item) => item.partnerId === partnerId);
  const withdrawals = withdrawalFixtures.filter((item) => item.partnerId === partnerId);
  const pendingMinor = sum(
    commissions.filter((item) => item.status === "pending").map((item) => item.amountMinor)
  );
  const postedMinor = sum(
    commissions.filter((item) => item.status === "available").map((item) => item.amountMinor)
  );
  const paidMinor = sum(
    withdrawals.filter((item) => item.status === "paid").map((item) => item.amountMinor)
  );
  const reservedMinor = sum(
    withdrawals
      .filter((item) => item.status === "requested" || item.status === "processing")
      .map((item) => item.amountMinor)
  );
  return {
    availableMinor: Math.max(0, postedMinor - paidMinor - reservedMinor),
    pendingMinor,
    reservedMinor,
    lifetimeMinor: sum(commissions.map((item) => item.amountMinor)),
  };
}

function baseProfilePayload(partner: PartnerFixture): DemoRecord {
  return {
    partner_id: partner.partnerId,
    user_id: idOf(partner.user),
    display_label: nameOf(partner.user),
    username: usernameOf(partner.user),
    avatar_url: avatarOf(partner.user),
    status: partner.status,
    commission_bps: partner.commissionBps,
    welcome_message: "Спасибо, что помогаете новым пользователям знакомиться с сервисом.",
    pause_reason: partner.status === "paused" ? "Проверка реквизитов" : null,
    activated_at: partner.activatedAt,
    created_at: partner.activatedAt,
  };
}

function balancePayload(partnerId: number): DemoRecord {
  const balance = balanceFor(partnerId);
  return {
    currency: CURRENCY,
    currency_scale: CURRENCY_SCALE,
    available_minor: balance.availableMinor,
    pending_minor: balance.pendingMinor,
    reserved_minor: balance.reservedMinor,
    lifetime_earned_minor: balance.lifetimeMinor,
  };
}

function adminProfilePayload(partner: PartnerFixture): DemoRecord {
  const clients = clientFixtures.filter((item) => item.partnerId === partner.partnerId);
  const commissions = commissionFixtures.filter((item) => item.partnerId === partner.partnerId);
  const latestClient = [...clients].sort(
    (left, right) => stringDate(right.attributedAt) - stringDate(left.attributedAt)
  )[0];
  const balance = balanceFor(partner.partnerId);
  return {
    ...baseProfilePayload(partner),
    balances: [balancePayload(partner.partnerId)],
    clients_count: clients.length,
    latest_client: latestClient ? nameOf(latestClient.user) : null,
    payments_count: commissions.length,
    gross_minor: sum(commissions.map((item) => item.grossMinor)),
    earned_minor: sum(commissions.map((item) => item.amountMinor)),
    available_minor: balance.availableMinor,
    currency: CURRENCY,
  };
}

function clientPayload(client: ClientFixture): DemoRecord {
  return {
    partner_client_id: client.clientId,
    public_client_id: `C-${idOf(client.user)}`,
    label: nameOf(client.user),
    source: client.source,
    attributed_at: client.attributedAt,
    eligible_from: client.attributedAt,
    payments_count: client.payments.length,
    gross_minor: sum(client.payments.map(amountMinor)),
    currency: CURRENCY,
    currency_scale: CURRENCY_SCALE,
  };
}

function commissionPayload(commission: CommissionFixture): DemoRecord {
  return {
    commission_id: commission.commissionId,
    payment_id: paymentId(commission.payment),
    client_public_id: `C-${idOf(commission.client.user)}`,
    client_label: nameOf(commission.client.user),
    gross_amount_minor: commission.grossMinor,
    commission_amount_minor: commission.amountMinor,
    currency: CURRENCY,
    currency_scale: CURRENCY_SCALE,
    commission_bps: partnersById.get(commission.partnerId)?.commissionBps || 0,
    sale_mode: String(commission.payment.sale_mode || "") || null,
    provider: String(commission.payment.provider || "") || null,
    status: commission.status,
    exclusion_reason: null,
    source_paid_at: commission.sourcePaidAt,
    available_at: commission.availableAt,
    created_at: commission.sourcePaidAt,
    reversed_at: null,
  };
}

function withdrawalPayload(withdrawal: WithdrawalFixture, includeIdentity = false): DemoRecord {
  const partner = partnersById.get(withdrawal.partnerId);
  const payload: DemoRecord = {
    withdrawal_id: withdrawal.withdrawalId,
    partner_id: withdrawal.partnerId,
    method_id: withdrawal.methodId,
    method_type: withdrawal.methodId,
    method_snapshot: { label: withdrawal.methodId },
    amount_minor: withdrawal.amountMinor,
    currency: CURRENCY,
    currency_scale: CURRENCY_SCALE,
    settlement_asset: withdrawal.methodId === "crypto" ? "USDT" : null,
    network: withdrawal.methodId === "crypto" ? "TRC20" : null,
    status: withdrawal.status,
    status_version: 1,
    status_message: withdrawal.status === "failed" ? "Платёжный канал временно недоступен" : null,
    external_reference: withdrawal.status === "paid" ? `DEMO-${withdrawal.withdrawalId}` : null,
    settlement_amount: withdrawal.methodId === "crypto" ? "82.00" : null,
    masked_requisites: withdrawal.masked,
    requested_at: withdrawal.requestedAt,
    processing_at: withdrawal.processingAt,
    paid_at: withdrawal.paidAt,
    decided_at: withdrawal.decidedAt,
  };
  if (includeIdentity && partner) {
    payload.user_id = idOf(partner.user);
    payload.display_label = nameOf(partner.user);
    payload.username = usernameOf(partner.user);
    payload.avatar_url = avatarOf(partner.user);
  }
  return payload;
}

function applicationPayload(application: ApplicationFixture): DemoRecord {
  const decided =
    application.status === "pending"
      ? null
      : iso(stringDate(application.submittedAt) + DAY_MS, latestPaymentTime);
  return {
    application_id: application.applicationId,
    user_id: idOf(application.user),
    display_label: nameOf(application.user),
    username: usernameOf(application.user),
    avatar_url: avatarOf(application.user),
    message: application.message,
    status: application.status,
    submitted_at: application.submittedAt,
    decided_at: decided,
    decision_message:
      application.status === "rejected" ? "Нужны дополнительные сведения об аудитории" : null,
    approved_commission_bps: application.status === "approved" ? 3000 : null,
    welcome_message: application.status === "approved" ? "Добро пожаловать в программу" : null,
    reapply_allowed_at:
      application.status === "rejected"
        ? iso(latestPaymentTime + 30 * DAY_MS, latestPaymentTime)
        : null,
  };
}

function linksFor(partner: PartnerFixture): DemoRecord {
  const token = String(partner.user.referral_code || `DEMO${partner.partnerId}`);
  return {
    telegram: `https://t.me/demo_minishop_bot?start=p_${token}`,
    web: `https://demo.example/?partner=${token}`,
    telegram_enabled: true,
    web_enabled: true,
  };
}

function currentPartner(): PartnerFixture | undefined {
  return (
    partnerFixtures.find((partner) => idOf(partner.user) === currentUserId) || partnerFixtures[0]
  );
}

function paginatedPayload<T>(
  items: T[],
  path: string
): { items: T[]; total: number; limit: number; offset: number } {
  const params = queryParams(path);
  const page = paged(items, params, 200);
  return {
    items: page.items,
    total: page.total,
    limit: page.pageSize,
    offset: page.page * page.pageSize,
  };
}

function adminOverview(): DemoRecord {
  const balances = partnerFixtures.map((partner) => balanceFor(partner.partnerId));
  const paidWithdrawals = withdrawalFixtures.filter((item) => item.status === "paid");
  const requestedWithdrawals = withdrawalFixtures.filter(
    (item) => item.status === "requested" || item.status === "processing"
  );
  const points = new Map<string, { gross: number; commission: number; paid: number }>();
  for (const commission of commissionFixtures) {
    const date = commission.sourcePaidAt.slice(0, 10);
    const point = points.get(date) || { gross: 0, commission: 0, paid: 0 };
    point.gross += commission.grossMinor;
    point.commission += commission.amountMinor;
    points.set(date, point);
  }
  for (const withdrawal of paidWithdrawals) {
    const date = withdrawal.requestedAt.slice(0, 10);
    const point = points.get(date) || { gross: 0, commission: 0, paid: 0 };
    point.paid += withdrawal.amountMinor;
    points.set(date, point);
  }
  return {
    ok: true,
    currency: CURRENCY,
    currency_scale: CURRENCY_SCALE,
    metrics: {
      active_partners: partnerFixtures.filter((item) => item.status === "active").length,
      paused_partners: partnerFixtures.filter((item) => item.status === "paused").length,
      clients: clientFixtures.length,
      gross_minor: sum(commissionFixtures.map((item) => item.grossMinor)),
      commissions_minor: sum(commissionFixtures.map((item) => item.amountMinor)),
      pending_minor: sum(balances.map((item) => item.pendingMinor)),
      available_minor: sum(balances.map((item) => item.availableMinor)),
      paid_minor: sum(paidWithdrawals.map((item) => item.amountMinor)),
      requested_minor: sum(requestedWithdrawals.map((item) => item.amountMinor)),
    },
    series: [...points.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([date, point]) => ({
        date,
        gross_minor: point.gross,
        commission_minor: point.commission,
        paid_minor: point.paid,
      })),
  };
}

function partnerDetail(partner: PartnerFixture): DemoRecord {
  const clients = clientFixtures.filter((item) => item.partnerId === partner.partnerId);
  const commissions = commissionFixtures.filter((item) => item.partnerId === partner.partnerId);
  const withdrawals = withdrawalFixtures.filter((item) => item.partnerId === partner.partnerId);
  let runningBalance = 0;
  const ledger = [
    ...commissions
      .filter((item) => item.status === "available")
      .map((item) => ({
        createdAt: item.availableAt,
        kind: "commission_available",
        amountMinor: item.amountMinor,
        reference: String(item.commissionId),
      })),
    ...withdrawals
      .filter(
        (item) =>
          item.status === "paid" || item.status === "requested" || item.status === "processing"
      )
      .map((item) => ({
        createdAt: item.requestedAt,
        kind: item.status === "paid" ? "withdrawal_paid" : "withdrawal_reserved",
        amountMinor: -item.amountMinor,
        reference: String(item.withdrawalId),
      })),
  ]
    .sort((left, right) => stringDate(left.createdAt) - stringDate(right.createdAt))
    .map((item, index) => {
      runningBalance += item.amountMinor;
      return {
        ledger_entry_id: 50_000 + index,
        kind: item.kind,
        state: "posted",
        amount_minor: item.amountMinor,
        balance_after_minor: runningBalance,
        currency: CURRENCY,
        currency_scale: CURRENCY_SCALE,
        created_at: item.createdAt,
        internal_reference: item.reference,
      };
    })
    .reverse();
  return {
    ok: true,
    partner: { ...adminProfilePayload(partner), links: linksFor(partner) },
    clients: clients.map(clientPayload),
    clients_total: clients.length,
    commissions: commissions.map(commissionPayload),
    commissions_total: commissions.length,
    withdrawals: withdrawals.map((item) => withdrawalPayload(item, true)),
    withdrawals_total: withdrawals.length,
    ledger,
    audit: [
      {
        audit_event_id: 60_000 + partner.partnerId,
        event_type: "partner_activated",
        actor_type: "admin",
        actor_user_id: currentUserId,
        reason: `${partner.commissionBps / 100}%`,
        created_at: partner.activatedAt,
      },
    ],
  };
}

function partnerList(path: string): DemoRecord {
  const params = queryParams(path);
  const search = String(params.get("search") || "")
    .trim()
    .toLowerCase();
  const status = String(params.get("status") || "")
    .trim()
    .toLowerCase();
  const sort = String(params.get("sort") || "clients_desc")
    .trim()
    .toLowerCase();
  let profiles = partnerFixtures.filter((partner) => {
    if (status && status !== "all" && partner.status !== status) return false;
    if (!search) return true;
    return [partner.partnerId, idOf(partner.user), nameOf(partner.user), usernameOf(partner.user)]
      .join(" ")
      .toLowerCase()
      .includes(search);
  });
  const metrics = (partner: PartnerFixture): Record<string, number> => {
    const commissions = commissionFixtures.filter((item) => item.partnerId === partner.partnerId);
    return {
      clients: clientFixtures.filter((item) => item.partnerId === partner.partnerId).length,
      payments: commissions.length,
      gross: sum(commissions.map((item) => item.grossMinor)),
      earned: sum(commissions.map((item) => item.amountMinor)),
      available: balanceFor(partner.partnerId).availableMinor,
      created: stringDate(partner.activatedAt),
    };
  };
  const [sortKey, sortDirection] = sort.split("_");
  profiles = [...profiles].sort((left, right) => {
    const leftValue = metrics(left)[sortKey] ?? metrics(left).created;
    const rightValue = metrics(right)[sortKey] ?? metrics(right).created;
    return sortDirection === "asc" ? leftValue - rightValue : rightValue - leftValue;
  });
  const page = paginatedPayload(profiles, path);
  return {
    ok: true,
    partners: page.items.map(adminProfilePayload),
    total: page.total,
    limit: page.limit,
    offset: page.offset,
  };
}

function withdrawalMethods(): DemoRecord[] {
  return [
    {
      id: "bank_card",
      type: "bank_card",
      enabled: true,
      label: "Банковская карта",
      debit_currency: CURRENCY,
      currency_scale: CURRENCY_SCALE,
      min_amount_minor: 10_000,
      max_amount_minor: 500_000,
      fields: [{ id: "card_number", label: "Номер карты", required: true }],
      settlement_asset: null,
      networks: [],
      sort_order: 10,
      help_text: "",
    },
    {
      id: "sbp",
      type: "sbp",
      enabled: true,
      label: "СБП",
      debit_currency: CURRENCY,
      currency_scale: CURRENCY_SCALE,
      min_amount_minor: 10_000,
      max_amount_minor: 500_000,
      fields: [{ id: "phone", label: "Телефон", required: true }],
      settlement_asset: null,
      networks: [],
      sort_order: 20,
      help_text: "",
    },
    {
      id: "crypto",
      type: "crypto",
      enabled: true,
      label: "USDT",
      debit_currency: CURRENCY,
      currency_scale: CURRENCY_SCALE,
      min_amount_minor: 10_000,
      max_amount_minor: null,
      fields: [{ id: "address", label: "Адрес кошелька", required: true }],
      settlement_asset: "USDT",
      networks: [{ id: "TRC20", label: "TRC20" }],
      sort_order: 30,
      help_text: "",
    },
  ];
}

export function demoPartnerAttributionForPayment(paymentValue: unknown): {
  partnerId: string;
  partnerName: string;
  partnerHandle: string;
  rate: number;
  amount: number;
  status: CommissionStatus;
  commissionId: string;
} | null {
  const commission = commissionFixtures.find(
    (item) => paymentId(item.payment) === Number(paymentValue)
  );
  const partner = commission ? partnersById.get(commission.partnerId) : null;
  if (!commission || !partner) return null;
  return {
    partnerId: String(partner.partnerId),
    partnerName: nameOf(partner.user),
    partnerHandle: usernameOf(partner.user)
      ? `@${usernameOf(partner.user)}`
      : `#${idOf(partner.user)}`,
    rate: partner.commissionBps / 100,
    amount: commission.amountMinor / 10 ** CURRENCY_SCALE,
    status: commission.status,
    commissionId: `COM-${commission.commissionId}`,
  };
}

export function demoPartnerFixtureFacts(): DemoRecord {
  return {
    current_user_id: currentUserId,
    partner_user_ids: partnerFixtures.map((partner) => idOf(partner.user)),
    client_user_ids: clientFixtures.map((client) => idOf(client.user)),
    commissions: commissionFixtures.map((commission) => ({
      partner_id: commission.partnerId,
      client_user_id: idOf(commission.client.user),
      payment_id: paymentId(commission.payment),
    })),
  };
}

export const partnerProgramFixtureRuntime = {
  adminOverview,
  adminProfilePayload,
  applicationFixtures,
  applicationPayload,
  balancePayload,
  baseProfilePayload,
  clientFixtures,
  clientPayload,
  commissionFixtures,
  commissionPayload,
  currentPartner,
  linksFor,
  paginatedPayload,
  partnerDetail,
  partnerFixtures,
  partnerList,
  partnersById,
  withdrawalFixtures,
  withdrawalMethods,
  withdrawalPayload,
};
