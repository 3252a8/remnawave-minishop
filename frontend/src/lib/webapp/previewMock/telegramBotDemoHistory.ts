import type { PaymentHistoryItem } from "../paymentHistory";

const historyKey = "minishop-bot-demo-payment-history";

export function storeBotDemoPayments(payments: PaymentHistoryItem[]) {
  try {
    window.sessionStorage.setItem(historyKey, JSON.stringify(payments));
    return true;
  } catch {
    return false;
  }
}

export function readBotDemoPayments(): PaymentHistoryItem[] {
  if (
    typeof window === "undefined" ||
    !new URLSearchParams(window.location.search).has("bot_demo_history")
  ) {
    return [];
  }
  try {
    const rows: unknown = JSON.parse(window.sessionStorage.getItem(historyKey) || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}
