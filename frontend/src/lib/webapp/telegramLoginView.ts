type TranslateFn = (key: string) => string;

export interface TelegramLoginView {
  telegramLoginChecking: boolean;
  telegramLoginLabel: string;
  telegramLoginUnavailable: boolean;
  telegramLoginUnavailableMessage: string;
}

export interface TelegramLoginViewInput {
  authBusy: boolean;
  authStatus: string;
  demoAuthLogin: unknown;
  telegramLoginBusy: boolean;
  telegramMiniAppAuthAvailable: boolean;
  telegramOAuthClientId: number;
  telegramSdkStatus: string;
  t: TranslateFn;
}

export function computeTelegramLoginView({
  authBusy,
  authStatus,
  demoAuthLogin,
  telegramLoginBusy,
  telegramMiniAppAuthAvailable,
  telegramOAuthClientId,
  telegramSdkStatus,
  t,
}: TelegramLoginViewInput): TelegramLoginView {
  const demoLogin = Boolean(demoAuthLogin);
  const telegramLoginUnavailable =
    !demoLogin &&
    !telegramMiniAppAuthAvailable &&
    !telegramOAuthClientId &&
    telegramSdkStatus !== "loading";
  const telegramLoginChecking =
    telegramLoginBusy || (authBusy && authStatus === t("wa_auth_checking_telegram"));
  const telegramLoginLabel = telegramLoginUnavailable
    ? t("wa_login_telegram_unavailable_button")
    : telegramLoginChecking
      ? t("wa_auth_checking_telegram")
      : t("wa_login_telegram_button");
  const telegramLoginUnavailableMessage = demoLogin
    ? ""
    : telegramLoginUnavailable && telegramSdkStatus === "unavailable"
      ? t("wa_auth_telegram_unavailable")
      : telegramLoginUnavailable
        ? t("wa_auth_telegram_not_configured")
        : "";

  return {
    telegramLoginChecking,
    telegramLoginLabel,
    telegramLoginUnavailable,
    telegramLoginUnavailableMessage,
  };
}
