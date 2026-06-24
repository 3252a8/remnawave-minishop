type AccountUiStore = {
  continueTelegramLinkPendingAction: () => unknown;
  linkTelegramAndActivateTrial: () => unknown;
  linkTelegramAndClaimReferralWelcome: () => unknown;
  openLinkEmailDialog: (email: string) => unknown;
  openSetPasswordDialog: () => unknown;
};

type TelegramWebApp = {
  openTelegramLink?: (url: string) => void;
};

type AccountUiActionDeps = {
  accountStore: AccountUiStore;
  demoEmail: () => string;
  emailAuthEnabled: () => boolean;
  getTelegram: () => TelegramWebApp | null;
  getTelegramNotificationsStartLink: () => string;
  isDemoAuthLogin: () => boolean;
  markTelegramNotificationsBotOpened: (openedAt: number) => void;
  now?: () => number;
  openExternalLink: (url: string) => void;
  refreshTelegram: () => TelegramWebApp | null;
  setTelegram: (telegram: TelegramWebApp) => void;
  showToast: (message: unknown) => void;
  t: (key: string) => unknown;
};

export function createAccountUiActions({
  accountStore,
  demoEmail,
  emailAuthEnabled,
  getTelegram,
  getTelegramNotificationsStartLink,
  isDemoAuthLogin,
  markTelegramNotificationsBotOpened,
  now = Date.now,
  openExternalLink,
  refreshTelegram,
  setTelegram,
  showToast,
  t,
}: AccountUiActionDeps) {
  function openSettingsLinkEmailDialog() {
    if (!emailAuthEnabled()) return;
    accountStore.openLinkEmailDialog(isDemoAuthLogin() ? demoEmail() : "");
  }

  function openSettingsSetPasswordDialog() {
    if (!emailAuthEnabled()) return;
    accountStore.openSetPasswordDialog();
  }

  function continueTelegramLinkPendingAction() {
    return accountStore.continueTelegramLinkPendingAction();
  }

  function linkTelegramAndActivateTrial() {
    return accountStore.linkTelegramAndActivateTrial();
  }

  function linkTelegramAndClaimReferralWelcome() {
    return accountStore.linkTelegramAndClaimReferralWelcome();
  }

  function openTelegramNotificationsBot() {
    const link = getTelegramNotificationsStartLink();
    markTelegramNotificationsBotOpened(now());
    if (!link) {
      showToast(t("wa_telegram_notifications_link_unavailable"));
      return;
    }
    const currentTg = getTelegram() || refreshTelegram();
    if (currentTg?.openTelegramLink && /^https:\/\/t\.me\//i.test(link)) {
      try {
        setTelegram(currentTg);
        currentTg.openTelegramLink(link);
        return;
      } catch {
        // Fall back to generic external opening below.
      }
    }
    openExternalLink(link);
  }

  return {
    continueTelegramLinkPendingAction,
    linkTelegramAndActivateTrial,
    linkTelegramAndClaimReferralWelcome,
    openSettingsLinkEmailDialog,
    openSettingsSetPasswordDialog,
    openTelegramNotificationsBot,
  };
}
