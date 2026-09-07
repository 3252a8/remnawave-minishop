import { describe, expect, it } from "vitest";

import { canRevokePaidGift, giftRefundWarningKey } from "./giftRevoke.js";

describe("gift revoke controls", () => {
  const gift = { status: "ready", payment_status: "succeeded", total_amount: 100 };

  it("only permits paid ready gifts", () => {
    expect(canRevokePaidGift(gift as never)).toBe(true);
    expect(canRevokePaidGift({ ...gift, status: "activating" } as never)).toBe(false);
    expect(canRevokePaidGift({ ...gift, total_amount: 0 } as never)).toBe(false);
  });

  it("warns when a credited balance is disabled", () => {
    expect(giftRefundWarningKey(false)).toBe("gifts_revoke_balance_disabled");
    expect(giftRefundWarningKey(true)).toBe("gifts_revoke_refund_hint");
  });
});
