import { telegramName } from "./formatters.js";
import { resolveProfileAvatarUrl } from "./gravatar.js";

type WebappRecord = Record<string, unknown>;
type TranslateFn = (key: string) => string;

type UserProfile = WebappRecord & {
  email?: string;
  telegram_id?: number | string;
  telegram_linked?: boolean;
  telegram_notifications_need_prompt?: boolean;
  telegram_notifications_start_link?: string;
  telegram_notifications_status?: string;
};

export interface AccountView {
  emailLinkStatus: string;
  hasUnlinkedIdentity: boolean;
  privacyPolicyUrl: string;
  profileAvatarUrl: string;
  profileEmail: string;
  profileTelegramId: string;
  serverStatusUrl: string;
  supportUrl: string;
  telegramNotificationsNeedPrompt: boolean;
  telegramNotificationsStartLink: string;
  telegramNotificationsStatus: string;
  telegramProfileName: string;
  userAgreementUrl: string;
}

export interface AccountViewInput {
  appSettings: WebappRecord | null | undefined;
  cfg: WebappRecord;
  emailAuthEnabled: boolean;
  emailAvatarUrl: string;
  t: TranslateFn;
  user: UserProfile;
}

export function computeAccountView({
  appSettings,
  cfg,
  emailAuthEnabled,
  emailAvatarUrl,
  t,
  user,
}: AccountViewInput): AccountView {
  const telegramNotificationsStatus = String(user?.telegram_notifications_status || "unknown");
  const telegramNotificationsNeedPrompt = Boolean(
    user?.telegram_linked && user?.telegram_notifications_need_prompt
  );
  const telegramNotificationsStartLink = String(user?.telegram_notifications_start_link || "");
  const hasUnlinkedIdentity = Boolean(
    !user?.telegram_linked || (emailAuthEnabled && !user?.email) || telegramNotificationsNeedPrompt
  );
  const telegramProfileName = telegramName(user);

  return {
    emailLinkStatus: user?.email ? t("wa_settings_linked") : t("wa_settings_email_not_linked"),
    hasUnlinkedIdentity,
    privacyPolicyUrl: String(cfg.privacyPolicyUrl || "").trim(),
    profileAvatarUrl: resolveProfileAvatarUrl(user, emailAvatarUrl),
    profileEmail: user?.email || t("wa_settings_email_not_linked"),
    profileTelegramId: user?.telegram_id ? `TG ID ${user.telegram_id}` : t("wa_tg_id_not_linked"),
    serverStatusUrl: String(appSettings?.server_status_url || cfg.serverStatusUrl || "").trim(),
    supportUrl: String(appSettings?.support_url || cfg.supportUrl || "").trim(),
    telegramNotificationsNeedPrompt,
    telegramNotificationsStartLink,
    telegramNotificationsStatus,
    telegramProfileName,
    userAgreementUrl: String(cfg.userAgreementUrl || "").trim(),
  };
}
