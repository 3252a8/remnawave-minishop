import { describe, expect, it } from "vitest";

import { formatReceivedSince, referralStats } from "./referralStats.js";

describe("referralStats", () => {
  it("reads the invitation counters and a complete received total", () => {
    expect(
      referralStats({ invited_count: 4, purchased_count: 2, received_bonus_days: 14 })
    ).toEqual({ invited: 4, paid: 2, received: { days: 14, since: null } });
  });

  it("keeps a complete total of zero visible", () => {
    expect(referralStats({ received_bonus_days: 0, received_bonus_since: null }).received).toEqual({
      days: 0,
      since: null,
    });
  });

  it("shows a dated total once a bonus lands after the ledger start", () => {
    const since = "2026-10-01T12:00:00+00:00";
    expect(referralStats({ received_bonus_days: 7, received_bonus_since: since }).received).toEqual(
      { days: 7, since }
    );
  });

  it("hides a dated total until the first recorded bonus", () => {
    expect(
      referralStats({ received_bonus_days: 0, received_bonus_since: "2026-10-01T12:00:00+00:00" })
        .received
    ).toBeNull();
  });

  it("hides the total when the backend cannot provide it", () => {
    expect(referralStats({ received_bonus_days: null }).received).toBeNull();
    expect(referralStats({}).received).toBeNull();
    expect(referralStats({ received_bonus_days: "7" }).received).toBeNull();
    expect(
      referralStats({ received_bonus_days: 7, received_bonus_since: "not a date" }).received
    ).toBeNull();
  });

  it("falls back to zero for missing or malformed counters", () => {
    expect(referralStats(undefined)).toEqual({ invited: 0, paid: 0, received: null });
    expect(referralStats({ invited_count: -3, purchased_count: "x" })).toMatchObject({
      invited: 0,
      paid: 0,
    });
  });
});

describe("formatReceivedSince", () => {
  it("formats the ledger start as a date in the given locale", () => {
    expect(formatReceivedSince("2026-10-01T12:00:00+00:00", "ru")).toMatch(/окт.*2026/);
    expect(formatReceivedSince("2026-10-01T12:00:00+00:00", "en")).toMatch(/Oct.*2026/);
  });
});
