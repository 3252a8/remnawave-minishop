export type ReceivedReferralBonus = {
  days: number;
  /** ISO time the count starts from when older bonuses were never recorded. */
  since: string | null;
};

export type ReferralStats = {
  invited: number;
  paid: number;
  /** `null` while there is no exact figure to show. */
  received: ReceivedReferralBonus | null;
};

type ReferralStatsSource = {
  invited_count?: unknown;
  purchased_count?: unknown;
  received_bonus_days?: unknown;
  received_bonus_since?: unknown;
};

function count(value: unknown): number {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.floor(number) : 0;
}

function receivedBonus(
  source: ReferralStatsSource | null | undefined
): ReceivedReferralBonus | null {
  const days = source?.received_bonus_days;
  if (typeof days !== "number" || !Number.isFinite(days) || days < 0) return null;
  const rawSince = source?.received_bonus_since;
  if (rawSince === null || rawSince === undefined || rawSince === "") {
    return { days: Math.floor(days), since: null };
  }
  if (typeof rawSince !== "string" || Number.isNaN(Date.parse(rawSince))) return null;
  // A count that starts at the ledger date says nothing until a bonus lands in it.
  return days > 0 ? { days: Math.floor(days), since: rawSince } : null;
}

export function referralStats(referral: ReferralStatsSource | null | undefined): ReferralStats {
  return {
    invited: count(referral?.invited_count),
    paid: count(referral?.purchased_count),
    received: receivedBonus(referral),
  };
}

export function formatReceivedSince(value: string, locale?: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(new Date(value));
}
