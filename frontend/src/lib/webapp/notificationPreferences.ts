export type NotificationPreferences = {
  marketing_email: boolean;
  marketing_telegram: boolean;
  system_email: boolean;
  system_telegram: boolean;
};

export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  marketing_email: true,
  marketing_telegram: true,
  system_email: true,
  system_telegram: true,
};

export function normalizeNotificationPreferences(value: unknown): NotificationPreferences {
  const record = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  return {
    marketing_email: record.marketing_email !== false,
    marketing_telegram: record.marketing_telegram !== false,
    system_email: record.system_email !== false,
    system_telegram: record.system_telegram !== false,
  };
}
