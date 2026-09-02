import type { DemoRecord } from "./dataset";

type BalanceSnapshot = DemoRecord & {
  amount: string;
  amount_minor: number;
  currency: string;
  currency_scale: number;
  enabled: boolean;
  history: DemoRecord[];
  sources: DemoRecord[];
  topup_min_amount: number;
  topup_max_amount: number;
  topup_presets: number[];
};

const seededBalances = new Map<number, BalanceSnapshot>();

function createSnapshot(userId: number, rich = false, enabled = true): BalanceSnapshot {
  const amountMinor = rich ? 128_450 : 18_000 + (Math.abs(userId) % 17) * 2_500;
  const partnerMinor = rich ? 36_200 : 5_000 + (Math.abs(userId) % 9) * 1_000;
  const now = Date.now();
  return {
    ok: true,
    enabled,
    currency: "RUB",
    currency_scale: 2,
    amount_minor: amountMinor,
    amount: (amountMinor / 100).toFixed(2),
    topup_min_amount: 100,
    topup_max_amount: 50_000,
    topup_presets: [300, 500, 1_000, 2_000],
    sources: [
      {
        id: "user",
        available: true,
        currency: "RUB",
        amount_minor: amountMinor,
        amount: (amountMinor / 100).toFixed(2),
      },
      {
        id: "partner",
        available: true,
        convertible: true,
        currency: "RUB",
        amount_minor: partnerMinor,
        amount: (partnerMinor / 100).toFixed(2),
      },
    ],
    history: [
      {
        entry_id: userId * 10 + 6,
        amount_minor: 50_000,
        kind: "payment_topup",
        state: "posted",
        reference_type: "payment",
        reference_id: `demo-payment-${userId}`,
        reason: "CloudPayments",
        created_at: new Date(now - 2 * 86_400_000).toISOString(),
      },
      {
        entry_id: userId * 10 + 5,
        amount_minor: -19_000,
        kind: "checkout_spend",
        state: "posted",
        reference_type: "payment",
        reference_id: `demo-order-${userId}`,
        reason: "Продление тарифа «Стандарт»",
        created_at: new Date(now - 3 * 86_400_000).toISOString(),
      },
      {
        entry_id: userId * 10 + 4,
        amount_minor: 12_000,
        kind: "partner_conversion_in",
        state: "posted",
        reference_type: "partner_balance",
        reference_id: `demo-conversion-${userId}`,
        reason: "Конвертация бонусов",
        created_at: new Date(now - 5 * 86_400_000).toISOString(),
      },
      {
        entry_id: userId * 10 + 3,
        amount_minor: -7_900,
        kind: "checkout_spend",
        state: "posted",
        reference_type: "payment",
        reference_id: `demo-device-${userId}`,
        reason: "Дополнительное устройство",
        created_at: new Date(now - 9 * 86_400_000).toISOString(),
      },
      {
        entry_id: userId * 10 + 2,
        amount_minor: 75_000,
        kind: "admin_adjustment",
        state: "posted",
        reference_type: "admin",
        reference_id: `demo-admin-${userId}`,
        reason: "Бонус за участие в тестировании",
        created_at: new Date(now - 14 * 86_400_000).toISOString(),
      },
    ],
  };
}

function source(snapshot: BalanceSnapshot, id: "user" | "partner"): DemoRecord {
  return snapshot.sources.find((item) => item.id === id) || {};
}

function syncMain(snapshot: BalanceSnapshot): void {
  const main = source(snapshot, "user");
  const factor = 10 ** snapshot.currency_scale;
  snapshot.amount_minor = Number(main.amount_minor || 0);
  snapshot.amount = (snapshot.amount_minor / factor).toFixed(snapshot.currency_scale);
  main.amount = snapshot.amount;
}

function addHistory(
  snapshot: BalanceSnapshot,
  amountMinor: number,
  kind: string,
  reason: string
): void {
  snapshot.history.unshift({
    entry_id: Date.now(),
    amount_minor: amountMinor,
    kind,
    state: "posted",
    reference_type: "admin",
    reference_id: `demo-${Date.now()}`,
    reason,
    created_at: new Date().toISOString(),
  });
  snapshot.history = snapshot.history.slice(0, 12);
}

export function currentDemoBalance(): BalanceSnapshot {
  const userId = 100_200_300;
  if (!seededBalances.has(userId)) seededBalances.set(userId, createSnapshot(userId, true, false));
  return seededBalances.get(userId)!;
}

export function adminDemoBalance(userId: number): BalanceSnapshot {
  if (!seededBalances.has(userId)) {
    seededBalances.set(userId, createSnapshot(userId, userId === 910001));
  }
  return seededBalances.get(userId)!;
}

export function applyDemoBalanceAdjustment(userId: number, body: DemoRecord): BalanceSnapshot {
  const snapshot = adminDemoBalance(userId);
  const main = source(snapshot, "user");
  const before = Number(main.amount_minor || 0);
  const requested = Math.round(Number(body.amount || 0) * 10 ** snapshot.currency_scale);
  const mode = String(body.mode || "add");
  const after =
    mode === "set" ? requested : before + (mode === "subtract" ? -requested : requested);
  if (after < 0) return snapshot;
  main.amount_minor = after;
  syncMain(snapshot);
  addHistory(
    snapshot,
    after - before,
    "admin_adjustment",
    String(body.reason || "Demo admin operation")
  );
  return snapshot;
}

export function applyDemoBalanceConversion(userId: number, body: DemoRecord): BalanceSnapshot {
  const snapshot = adminDemoBalance(userId);
  const main = source(snapshot, "user");
  const partner = source(snapshot, "partner");
  const factor = 10 ** snapshot.currency_scale;
  const amountMinor = Math.round(Number(body.amount || 0) * factor);
  const direction = String(body.direction || "partner_to_user");
  const from = direction === "partner_to_user" ? partner : main;
  const to = direction === "partner_to_user" ? main : partner;
  if (amountMinor <= 0 || Number(from.amount_minor || 0) < amountMinor) return snapshot;
  from.amount_minor = Number(from.amount_minor || 0) - amountMinor;
  to.amount_minor = Number(to.amount_minor || 0) + amountMinor;
  from.amount = (Number(from.amount_minor || 0) / factor).toFixed(snapshot.currency_scale);
  to.amount = (Number(to.amount_minor || 0) / factor).toFixed(snapshot.currency_scale);
  syncMain(snapshot);
  addHistory(
    snapshot,
    direction === "partner_to_user" ? amountMinor : -amountMinor,
    direction === "partner_to_user" ? "partner_conversion_in" : "partner_conversion_out",
    String(body.reason || "Demo balance conversion")
  );
  return snapshot;
}
