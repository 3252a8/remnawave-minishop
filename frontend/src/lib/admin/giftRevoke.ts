import type { components } from "$lib/api/openapi.generated.js";

type AdminGift = components["schemas"]["AdminGiftView"];

export function canRevokePaidGift(gift: AdminGift): boolean {
  return gift.status === "ready" && gift.payment_status === "succeeded" && gift.total_amount > 0;
}

export function giftRefundWarningKey(balanceEnabled: boolean): string {
  return balanceEnabled ? "gifts_revoke_refund_hint" : "gifts_revoke_balance_disabled";
}
