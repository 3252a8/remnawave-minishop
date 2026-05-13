import {
  readMagicLoginToken,
  readTelegramAuthStatus,
  readTelegramLoginWidgetAuthData,
  clearAuthQuery,
} from "./authHelpers.js";
import { TELEGRAM_SDK_BOOT_TIMEOUT_MS } from "./constants.js";

/**
 * Initial auth / session bootstrap for the subscription webapp (non-preview).
 * Keeps side effects in App (mode, tg, token) via injected callbacks.
 */
export async function runWebappBoot({
  MOCK,
  setMode,
  hasTelegramLaunchParams,
  loadTelegramSdk,
  prepareTelegramMiniApp,
  loadData,
  showLogin,
  clearToken,
  clearManualLogoutFlag,
  isManuallyLoggedOut,
  finalizeMagicLogin,
  finalizeTelegramAuth,
  setAuthStatus,
  t,
  getInitDataForBoot,
  getToken,
  getCsrfToken,
}) {
  setMode("loading");
  if (hasTelegramLaunchParams()) await loadTelegramSdk(TELEGRAM_SDK_BOOT_TIMEOUT_MS);
  prepareTelegramMiniApp();

  if (MOCK) {
    await loadData();
    return;
  }

  const magicToken = readMagicLoginToken();
  if (magicToken && (await finalizeMagicLogin(magicToken))) return;

  const telegramAuthStatus = readTelegramAuthStatus();
  if (telegramAuthStatus === "success") {
    clearManualLogoutFlag();
    clearAuthQuery();
    try {
      await loadData();
      return;
    } catch {
      clearToken();
    }
  } else if (telegramAuthStatus) {
    clearAuthQuery();
    setAuthStatus(
      telegramAuthStatus === "cancelled"
        ? t("wa_auth_telegram_cancelled")
        : t("wa_auth_telegram_not_confirmed"),
      true
    );
  }

  if (isManuallyLoggedOut()) {
    showLogin();
    return;
  }

  const widgetAuthData = readTelegramLoginWidgetAuthData();
  if (widgetAuthData && (await finalizeTelegramAuth(widgetAuthData, "auth_data"))) return;

  const initData = getInitDataForBoot();
  if (initData) {
    try {
      if (await finalizeTelegramAuth(initData, "init_data")) return;
    } catch (_error) {
      void _error;
    }
  }

  if (getToken() || getCsrfToken()) {
    try {
      await loadData();
      return;
    } catch {
      clearToken();
    }
  }

  showLogin();
}
