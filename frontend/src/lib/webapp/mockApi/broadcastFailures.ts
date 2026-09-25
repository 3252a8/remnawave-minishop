import { demoBroadcasts } from "./state";

export function demoBroadcastFailures(broadcastId: number, params: URLSearchParams) {
  if (!demoBroadcasts().some((item) => Number(item.broadcast_id) === broadcastId)) {
    return { ok: false, error: "broadcast_not_found" };
  }
  const failures =
    broadcastId === 101
      ? [
          {
            delivery_id: 1,
            user_id: 100241,
            channel: "telegram",
            error: "Telegram server says - Forbidden: bot was blocked by the user",
          },
          {
            delivery_id: 2,
            user_id: 100242,
            channel: "telegram",
            error: "Telegram server says - Forbidden: bot was blocked by the user",
          },
          {
            delivery_id: 3,
            user_id: 100243,
            channel: "telegram",
            error: "Telegram server says - Forbidden: bot was blocked by the user",
          },
          {
            delivery_id: 4,
            user_id: 100244,
            channel: "telegram",
            error: "Telegram server says - Bad Request: chat not found",
          },
          { delivery_id: 5, user_id: 100245, channel: "telegram", error: "message_too_long" },
        ]
      : [];
  const offset = Math.max(0, Number(params.get("offset") || 0));
  const limit = Math.min(100, Math.max(1, Number(params.get("limit") || 50)));
  return {
    ok: true,
    total: failures.length,
    failures: failures.slice(offset, offset + limit),
  };
}
