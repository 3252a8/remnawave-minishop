import {
  readMagicLoginToken,
  readTelegramAuthStatus,
  readTelegramLoginWidgetAuthData,
  clearAuthQuery,
} from "./authHelpers.js";
import { TELEGRAM_SDK_BOOT_TIMEOUT_MS } from "./constants";

type SessionRefreshResult = {
  authenticated?: boolean;
  csrf_token?: string;
};

export type WebappBootDeps = {
  MOCK: unknown;
  setMode: (mode: string) => void;
  hasTelegramLaunchParams: () => boolean;
  loadTelegramSdk: (timeoutMs?: number) => Promise<unknown> | unknown;
  prepareTelegramMiniApp: () => void;
  loadData: () => Promise<unknown>;
  showLogin: () => void;
  clearToken: () => void;
  refreshSession?: (() => Promise<SessionRefreshResult | null | undefined>) | null;
  setCsrfToken?: ((csrfToken: string) => void) | null;
  clearManualLogoutFlag: () => void;
  isManuallyLoggedOut: () => boolean;
  hasEmailCodeLoginDeeplink?: (() => boolean) | null;
  finalizeMagicLogin: (token: string) => unknown;
  finalizeTelegramAuth: (authData: unknown, source: "auth_data" | "init_data") => unknown;
  setAuthStatus: (message: string, isError?: boolean) => void;
  t: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  getInitDataForBoot: () => string | null | undefined;
  getToken: () => string | null | undefined;
  getCsrfToken: () => string | null | undefined;
};

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
  refreshSession,
  setCsrfToken,
  clearManualLogoutFlag,
  isManuallyLoggedOut,
  hasEmailCodeLoginDeeplink,
  finalizeMagicLogin,
  finalizeTelegramAuth,
  setAuthStatus,
  t,
  getInitDataForBoot,
  getToken,
  getCsrfToken,
}: WebappBootDeps): Promise<void> {
  setMode("loading");
  if (hasTelegramLaunchParams()) await loadTelegramSdk(TELEGRAM_SDK_BOOT_TIMEOUT_MS);
  prepareTelegramMiniApp();

  if (MOCK) {
    await loadData();
    return;
  }

  if (hasEmailCodeLoginDeeplink?.()) {
    clearManualLogoutFlag();
    clearToken();
    showLogin();
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
        : telegramAuthStatus === "invite_required"
          ? t("wa_auth_invite_required")
          : t("wa_auth_telegram_not_confirmed"),
      true
    );
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

  if (isManuallyLoggedOut()) {
    showLogin();
    return;
  }

  if (refreshSession) {
    try {
      const session = await refreshSession();
      if (session?.authenticated) {
        if (session.csrf_token) setCsrfToken?.(session.csrf_token);
        clearManualLogoutFlag();
        await loadData();
        return;
      }
    } catch {
      clearToken();
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
