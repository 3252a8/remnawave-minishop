import { describe, expect, it } from "vitest";
import { broadcastFailureKind, broadcastFailuresFromWire } from "./broadcastFailures";

describe("broadcast delivery failures", () => {
  it("explains a newly discovered Telegram block without classifying email failures as blocks", () => {
    const detail = "Telegram server says - Forbidden: bot was blocked by the user";
    expect(broadcastFailureKind(detail, "telegram")).toBe("blocked");
    expect(broadcastFailureKind(detail, "email")).toBe("email");
    expect(broadcastFailureKind("message_too_long", "telegram")).toBe("content");
    expect(broadcastFailureKind("Bad Request: chat not found", "telegram")).toBe("unavailable");
  });

  it("keeps the total while parsing a page of failures", () => {
    expect(
      broadcastFailuresFromWire({
        total: 5,
        failures: [
          {
            delivery_id: 4,
            user_id: 123,
            channel: "telegram",
            error: "Forbidden: bot was blocked by the user",
            finished_at: "2026-09-25T18:30:00Z",
          },
        ],
      })
    ).toMatchObject({
      total: 5,
      failures: [{ deliveryId: 4, userId: 123, channel: "telegram" }],
    });
  });
});
