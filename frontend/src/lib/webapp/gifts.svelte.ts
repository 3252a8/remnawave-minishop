import type { components } from "$lib/api/openapi.generated.js";
import type { PendingPaymentView } from "$lib/webapp/types.js";

export type GiftView = components["schemas"]["GiftView"];
const STORAGE_KEY = "minishop.pendingGift";
const QUEUE_KEY = "minishop.savedGifts";
function savedTokens(): string[] {
  const raw: unknown = JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
  return Array.isArray(raw)
    ? raw.filter(
        (token): token is string => typeof token === "string" && /^[A-Za-z0-9_-]{43}$/.test(token)
      )
    : [];
}

function readGiftToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const query = new URLSearchParams(window.location.search);
    const saved = savedTokens();
    const previous = localStorage.getItem(STORAGE_KEY) || "";
    const token = query.get("gift") || previous || saved[0] || "";
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return query.get("gift") ? "X".repeat(43) : "";
    localStorage.setItem(STORAGE_KEY, token);
    localStorage.setItem(
      QUEUE_KEY,
      JSON.stringify([
        ...new Set(
          [token, ...saved, previous].filter((value) => /^[A-Za-z0-9_-]{43}$/.test(value))
        ),
      ])
    );
    return token;
  } catch {
    return new URLSearchParams(window.location.search).get("gift") || "";
  }
}

export const giftState = $state({
  token: readGiftToken(),
  incoming: true,
  open: false,
  purchaseRequested: false,
  enabled: false,
  revision: 0,
  gifts: [] as GiftView[],
  loading: false,
  error: "",
  pending: null as PendingPaymentView | null,
  receiptId: 0,
  recipientEmail: "",
});

export function forgetGift(): void {
  const consumed = giftState.token;
  giftState.token = "";
  try {
    const remaining = savedTokens().filter((token) => token !== consumed);
    localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
    localStorage.removeItem(STORAGE_KEY);
    giftState.token = remaining[0] || "";
  } catch {
    /* Storage may be unavailable in private browsing. */
  }
  const url = new URL(window.location.href);
  url.searchParams.delete("gift");
  window.history.replaceState(window.history.state, "", url);
}
