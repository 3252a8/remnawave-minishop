import {
  readMagicLoginToken,
  readExternalAuthStatus,
  readTelegramAuthStatus,
  readTelegramLoginWidgetAuthData,
  clearAuthQuery,
} from "./authHelpers.js";
import { TELEGRAM_SDK_BOOT_TIMEOUT_MS } from "./constants";
import {
  beginBootBudget,
  finishBootBudget,
  WEBAPP_BOOT_BUDGET_MS,
  currentBootSignal,
  isInvalidSession,
  recordClientTiming,
} from "./bootBudget";

type SessionRefreshResult = {
  authenticated?: boolean;
  csrf_token?: string;
};

const BOOT_RETRY_WINDOW_MS = 90_000;
const BOOT_RETRY_MAX_DELAY_MS = 4_000;
let activeBootRun = 0;

function isTemporaryServiceFailure(error: unknown): boolean {
  if (error instanceof TypeError) return true; // Fetch rejects with TypeError while the API is offline.
  if (!error || typeof error !== "object" || !("status" in error)) return false;
  const status = Number(error.status);
  return status === 429 || (status >= 500 && status < 600);
}

function accountMergeConflictMessage(status: string, t: WebappBootDeps["t"]): string {
  const keyByStatus: Record<string, string> = {
    account_merge_google_conflict: "account_merge_google_conflict",
    account_merge_yandex_conflict: "account_merge_yandex_conflict",
    account_merge_provider_conflict: "account_merge_provider_conflict",
    account_merge_telegram_conflict: "account_merge_telegram_conflict",
    account_merge_duplicate_promo_conflict: "account_merge_duplicate_promo_conflict",
  };
  return t(keyByStatus[status] || "account_merge_conflict");
}

function isAccountMergeConflict(status: string): boolean {
  return status.startsWith("account_merge_");
}

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
  linkTelegramAfterExternalAuth?: (() => Promise<unknown> | unknown) | null;
  restorePendingExternalOauth: () => Promise<boolean> | boolean;
  setAuthStatus: (message: string, isError?: boolean) => void;
  showAccountLinkStatus?: ((message: string) => void) | null;
  t: (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  getInitDataForBoot: () => string | null | undefined;
  getToken: () => string | null | undefined;
  getCsrfToken: () => string | null | undefined;
};

/**
 * Initial auth / session bootstrap for the subscription webapp (non-preview).
 * Keeps side effects in App (mode, tg, token) via injected callbacks.
 */
export async function runWebappBoot(deps: WebappBootDeps): Promise<void> {
  const bootRun = ++activeBootRun;
  const retryUntil = Date.now() + BOOT_RETRY_WINDOW_MS;
  let retryDelay = 1_000;
  while (bootRun === activeBootRun) {
    const controller = beginBootBudget();
    const started = performance.now();
    let outcome = "ok";
    const step = async <T>(call: () => T | Promise<T>): Promise<T> => {
      if (controller.signal.aborted) throw new DOMException("boot_cancelled", "AbortError");
      const result = await call();
      if (controller.signal.aborted) throw new DOMException("boot_cancelled", "AbortError");
      return result;
    };
    let abortListener = () => {};
    const aborted = new Promise<never>((_resolve, reject) => {
      abortListener = () => reject(new DOMException("boot_timeout", "AbortError"));
      controller.signal.addEventListener("abort", abortListener, { once: true });
    });
    const timer = setTimeout(() => controller.abort(), WEBAPP_BOOT_BUDGET_MS);
    let retry = false;
    try {
      await Promise.race([
        runWebappBootSequence({
          ...deps,
          setMode: (mode) => {
            if (!controller.signal.aborted) deps.setMode(mode);
          },
          clearToken: () => {
            if (!controller.signal.aborted) deps.clearToken();
          },
          showLogin: () => {
            if (!controller.signal.aborted) deps.showLogin();
          },
          setAuthStatus: (message, error) => {
            if (!controller.signal.aborted) deps.setAuthStatus(message, error);
          },
          loadData: () => step(deps.loadData),
          loadTelegramSdk: (timeout) => step(() => deps.loadTelegramSdk(timeout)),
          refreshSession: deps.refreshSession ? () => step(() => deps.refreshSession?.()) : null,
          finalizeMagicLogin: (token) => step(() => deps.finalizeMagicLogin(token)),
          finalizeTelegramAuth: (data, source) =>
            step(() => deps.finalizeTelegramAuth(data, source)),
          restorePendingExternalOauth: () => step(deps.restorePendingExternalOauth),
        }),
        aborted,
      ]);
    } catch (error) {
      outcome = controller.signal.aborted ? "timeout_or_cancel" : "unavailable";
      retry =
        !controller.signal.aborted &&
        isTemporaryServiceFailure(error) &&
        Date.now() + retryDelay < retryUntil;
      if (!retry && currentBootSignal() === controller.signal) {
        deps.setMode("bootError");
        deps.setAuthStatus(deps.t("wa_boot_failed"), true);
      }
    } finally {
      clearTimeout(timer);
      controller.signal.removeEventListener("abort", abortListener);
      finishBootBudget(controller);
      recordClientTiming("boot", started, outcome);
      if (outcome === "ok") recordClientTiming("interactive", 0, outcome);
    }
    if (!retry || bootRun !== activeBootRun) return;
    // The frontend may become reachable before the API during a container restart.
    // Keep the initial loader visible and retry without discarding the saved session.
    await new Promise<void>((resolve) => setTimeout(resolve, retryDelay));
    retryDelay = Math.min(retryDelay * 2, BOOT_RETRY_MAX_DELAY_MS);
  }
}

async function runWebappBootSequence({
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
  linkTelegramAfterExternalAuth,
  restorePendingExternalOauth,
  setAuthStatus,
  showAccountLinkStatus,
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

  const externalAuth = readExternalAuthStatus();
  if (externalAuth?.status === "success") {
    clearManualLogoutFlag();
    clearAuthQuery();
    try {
      await loadData();
      try {
        await linkTelegramAfterExternalAuth?.();
      } catch {
        showAccountLinkStatus?.(t("wa_auth_telegram_not_confirmed"));
      }
      return;
    } catch (error) {
      if (!isInvalidSession(error)) throw error;
      clearToken();
    }
  } else if (externalAuth?.status === "email_confirmation_required") {
    clearManualLogoutFlag();
    clearToken();
    clearAuthQuery();
    showLogin();
    await restorePendingExternalOauth();
    return;
  } else if (externalAuth && isAccountMergeConflict(externalAuth.status)) {
    clearAuthQuery();
    try {
      await loadData();
      showAccountLinkStatus?.(accountMergeConflictMessage(externalAuth.status, t));
      return;
    } catch (error) {
      if (!isInvalidSession(error)) throw error;
      clearToken();
    }
  } else if (externalAuth) {
    clearAuthQuery();
    setAuthStatus(
      externalAuth.status === "account_exists"
        ? t("wa_auth_external_account_exists", { provider: externalAuth.provider })
        : externalAuth.status === "invite_required"
          ? t("wa_auth_invite_required")
          : externalAuth.status === "cancelled"
            ? t("wa_auth_external_cancelled")
            : t("wa_auth_external_failed"),
      true
    );
  }

  const telegramAuthStatus = readTelegramAuthStatus();
  if (telegramAuthStatus === "success") {
    clearManualLogoutFlag();
    clearAuthQuery();
    try {
      await loadData();
      return;
    } catch (error) {
      if (!isInvalidSession(error)) throw error;
      clearToken();
    }
  } else if (telegramAuthStatus && isAccountMergeConflict(telegramAuthStatus)) {
    clearAuthQuery();
    try {
      await loadData();
      showAccountLinkStatus?.(accountMergeConflictMessage(telegramAuthStatus, t));
      return;
    } catch (error) {
      if (!isInvalidSession(error)) throw error;
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
    } catch (error) {
      if (!isInvalidSession(error)) throw error;
      clearToken();
    }
  }

  if (getToken() || getCsrfToken()) {
    try {
      await loadData();
      return;
    } catch (error) {
      if (!isInvalidSession(error)) throw error;
      clearToken();
    }
  }

  showLogin();
}
