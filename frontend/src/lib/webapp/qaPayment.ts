import {
  buildPaymentStatusPath,
  buildQaPaymentCompletePath,
  unwrap,
  type ApiClient,
} from "./publicApi.js";

export type QaPaymentState = "failed" | "loading" | "pending" | "success" | "unavailable";

export function qaPaymentIdFromSearch(search: string): number | null {
  const raw = new URLSearchParams(search).get("qa_payment_id");
  if (!raw || !/^\d+$/.test(raw)) return null;
  const paymentId = Number(raw);
  return Number.isSafeInteger(paymentId) && paymentId > 0 ? paymentId : null;
}

export function isQaPaymentUrl(value: string): boolean {
  try {
    return qaPaymentIdFromSearch(new URL(value, "http://localhost").search) !== null;
  } catch {
    return false;
  }
}

export function qaPaymentStateForStatus(status: unknown): QaPaymentState {
  const normalized = String(status || "").trim().toLowerCase();
  if (normalized === "succeeded") return "success";
  if (normalized === "pending_qa") return "pending";
  return normalized ? "failed" : "unavailable";
}

export async function fetchQaPaymentState(
  api: ApiClient["api"],
  paymentId: number
): Promise<QaPaymentState> {
  const response = await api(buildPaymentStatusPath(paymentId));
  if (!response.ok) return "unavailable";
  return qaPaymentStateForStatus(unwrap(response).status);
}

export async function completeQaPayment(
  api: ApiClient["api"],
  paymentId: number
): Promise<QaPaymentState> {
  const response = await api(buildQaPaymentCompletePath(paymentId), { method: "POST" });
  if (!response.ok) {
    const error = String("error" in response ? response.error || "" : "");
    return error === "payment_not_pending" ? "failed" : "unavailable";
  }
  return fetchQaPaymentState(api, paymentId);
}

export function stripQaPaymentQuery(url: URL): string {
  url.searchParams.delete("qa_payment_id");
  return `${url.pathname}${url.search}${url.hash}`;
}
