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

function readGiftToken(): { token: string; entryIntent: boolean } {
  if (typeof window === "undefined") return { token: "", entryIntent: false };
  try {
    const query = new URLSearchParams(window.location.search);
    const queryToken = query.get("gift") || "";
    const saved = savedTokens();
    const previous = localStorage.getItem(STORAGE_KEY) || "";
    const token = queryToken || previous || saved[0] || "";
    if (!/^[A-Za-z0-9_-]{43}$/.test(token)) {
      return { token: queryToken ? "X".repeat(43) : "", entryIntent: Boolean(queryToken) };
    }
    localStorage.setItem(STORAGE_KEY, token);
    localStorage.setItem(
      QUEUE_KEY,
      JSON.stringify([
        ...new Set(
          [token, ...saved, previous].filter((value) => /^[A-Za-z0-9_-]{43}$/.test(value))
        ),
      ])
    );
    return { token, entryIntent: Boolean(queryToken) };
  } catch {
    const queryToken = new URLSearchParams(window.location.search).get("gift") || "";
    return { token: queryToken, entryIntent: Boolean(queryToken) };
  }
}

const initialGift = readGiftToken();
export const giftState = $state({
  token: initialGift.token,
  entryIntent: initialGift.entryIntent,
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
  giftState.entryIntent = false;
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
