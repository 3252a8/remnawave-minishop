import { fmtMoney } from "./format.js";
import { DEFAULT_PARTNER_LIST_QUERY, type AdminPartnerListQuery } from "./partnerProgramApi.js";

export const partnerTableLayouts = {
  partners: {
    columnWidths: ["23%", "13%", "8%", "9%", "12%", "12%", "13%", "10%"],
    minWidth: "980px",
  },
  applications: {
    columnWidths: ["17%", "23%", "23%", "15%", "12%", "10%"],
    minWidth: "940px",
  },
  withdrawals: {
    columnWidths: ["16%", "21%", "13%", "11%", "14%", "15%", "10%"],
    minWidth: "980px",
  },
};

export type PartnerStatusVariant = "success" | "warning" | "danger" | "muted";
export type PartnerWithdrawalTransition = "processing" | "paid" | "reject" | "fail";

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

/** Partner amounts use the admin money format: kopecks shown, ₽ for RUB. */
export function formatPartnerMoney(value: number, currency: string): string {
  return fmtMoney(value, currency);
}

export function partnerStatusVariant(status: string): PartnerStatusVariant {
  if (status === "active" || status === "approved" || status === "paid") return "success";
  if (status === "pending" || status === "requested" || status === "processing") return "warning";
  if (status === "rejected" || status === "closed" || status === "failed") return "danger";
  return "muted";
}

export function partnerStatusLabel(at: TranslateFn, status: string): string {
  return at(`partners_status_${status}`, {}, status);
}

export function partnerWithdrawalTransitionMessage(
  at: TranslateFn,
  status: PartnerWithdrawalTransition
): string {
  const copy: Record<PartnerWithdrawalTransition, [string, string]> = {
    processing: ["partners_withdrawal_processing", "Withdrawal moved to processing"],
    paid: ["partners_withdrawal_paid", "Withdrawal marked paid"],
    reject: ["partners_withdrawal_returned", "Withdrawal rejected and reserve released"],
    fail: ["partners_withdrawal_failed", "Withdrawal marked failed"],
  };
  return at(copy[status][0], {}, copy[status][1]);
}

export function partnerActionIdempotencyKey(prefix: string): string {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  return `${prefix}-${random}`;
}

export function partnerTopListQuery(sort: string): AdminPartnerListQuery {
  return { ...DEFAULT_PARTNER_LIST_QUERY, sort, limit: 6 };
}

export function shouldShowPartnerReferralImport(
  importable: number,
  conflicts: number,
  previewMode = false
): boolean {
  return previewMode || importable > 0 || conflicts > 0;
}
