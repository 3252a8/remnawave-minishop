export type BroadcastFailure = {
  deliveryId: number;
  userId: number;
  channel: string;
  error: string;
  finishedAt: string | null;
};

export type BroadcastFailuresPage = {
  total: number;
  failures: BroadcastFailure[];
};

export type BroadcastFailureKind =
  "blocked" | "unavailable" | "rate_limit" | "content" | "email" | "telegram";

export function broadcastFailureKind(error: string, channel: string): BroadcastFailureKind {
  const detail = error.toLowerCase();
  if (channel === "telegram") {
    if (/bot was blocked|blocked by the user/.test(detail)) return "blocked";
    if (/chat not found|user is deactivated|user not found|can't initiate/.test(detail)) {
      return "unavailable";
    }
    if (/retry after|too many requests|flood control/.test(detail)) return "rate_limit";
    if (
      /message_too_long|message is too long|caption is too long|can't parse entities/.test(detail)
    ) {
      return "content";
    }
    return "telegram";
  }
  return "email";
}

export function broadcastFailuresFromWire(value: unknown): BroadcastFailuresPage {
  if (!value || typeof value !== "object") return { total: 0, failures: [] };
  const payload = value as Record<string, unknown>;
  const total = Number(payload.total);
  const failures = Array.isArray(payload.failures)
    ? payload.failures.flatMap((raw) => {
        if (!raw || typeof raw !== "object") return [];
        const item = raw as Record<string, unknown>;
        const deliveryId = Number(item.delivery_id);
        const userId = Number(item.user_id);
        if (!Number.isFinite(deliveryId) || !Number.isFinite(userId)) return [];
        return [
          {
            deliveryId,
            userId,
            channel: String(item.channel || ""),
            error: String(item.error || "delivery_failed"),
            finishedAt: item.finished_at == null ? null : String(item.finished_at),
          },
        ];
      })
    : [];
  return { total: Number.isFinite(total) ? Math.max(0, total) : 0, failures };
}
