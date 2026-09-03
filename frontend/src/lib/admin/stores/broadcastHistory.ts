export type BroadcastHistoryButton = {
  kind: string;
  label: string;
  url: string;
  promoCode: string;
  section: string;
  labels: Record<string, string>;
};

export type BroadcastHistoryItem = {
  broadcastId: number;
  status: string;
  target: string;
  channels: string[];
  excludeBlockedTelegram: boolean;
  texts: Record<string, string>;
  emailSubjects: Record<string, string>;
  buttons: BroadcastHistoryButton[];
  imageId: string | null;
  scheduledAt: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  updatedAt: string;
  recipientCount: number;
  totalDeliveries: number;
  successfulDeliveries: number;
  failedDeliveries: number;
  telegramSent: number;
  telegramFailed: number;
  emailSent: number;
  emailFailed: number;
  lastError: string | null;
};

export function historyItemFromWire(value: unknown): BroadcastHistoryItem | null {
  if (!value || typeof value !== "object") return null;
  const item = value as Record<string, unknown>;
  const broadcastId = Number(item.broadcast_id);
  if (!Number.isFinite(broadcastId) || broadcastId <= 0) return null;
  const record = (input: unknown): Record<string, string> => {
    if (!input || typeof input !== "object" || Array.isArray(input)) return {};
    return Object.fromEntries(
      Object.entries(input as Record<string, unknown>).map(([key, text]) => [
        key,
        String(text || ""),
      ])
    );
  };
  const buttons = Array.isArray(item.buttons)
    ? item.buttons.map((raw) => {
        const button = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
        return {
          kind: String(button.kind || "url"),
          label: String(button.label || ""),
          url: String(button.url || ""),
          promoCode: String(button.promo_code || ""),
          section: String(button.section || ""),
          labels: record(button.labels),
        };
      })
    : [];
  const number = (key: string): number => {
    const parsed = Number(item[key]);
    return Number.isFinite(parsed) ? parsed : 0;
  };
  const nullableText = (key: string): string | null =>
    item[key] == null || item[key] === "" ? null : String(item[key]);
  return {
    broadcastId,
    status: String(item.status || "queued"),
    target: String(item.target || "all"),
    channels: Array.isArray(item.channels) ? item.channels.map(String) : [],
    excludeBlockedTelegram: Boolean(item.exclude_blocked_telegram),
    texts: record(item.texts),
    emailSubjects: record(item.email_subjects),
    buttons,
    imageId: nullableText("image_id"),
    scheduledAt: String(item.scheduled_at || ""),
    createdAt: String(item.created_at || ""),
    startedAt: nullableText("started_at"),
    finishedAt: nullableText("finished_at"),
    updatedAt: String(item.updated_at || ""),
    recipientCount: number("recipient_count"),
    totalDeliveries: number("total_deliveries"),
    successfulDeliveries: number("successful_deliveries"),
    failedDeliveries: number("failed_deliveries"),
    telegramSent: number("telegram_sent"),
    telegramFailed: number("telegram_failed"),
    emailSent: number("email_sent"),
    emailFailed: number("email_failed"),
    lastError: nullableText("last_error"),
  };
}
