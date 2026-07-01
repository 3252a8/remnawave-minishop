import {
  readReferralParam,
  clearAuthQuery,
  buildTelegramOAuthStartUrl,
  emailError,
} from "../authHelpers.js";
import type { LoadDataOptions } from "../dataClient";
import type { ApiClient, PostPayload } from "../publicApi";
import {
  buildAuthEmailMagicPath,
  buildAuthEmailPasswordPath,
  buildAuthEmailRequestPath,
  buildAuthEmailVerifyPath,
  buildAuthTokenPath,
  unwrap,
} from "../publicApi";

const EMAIL_CODE_PENDING_STORAGE_KEY = "rw_email_code_login_pending_v1";
const EMAIL_CODE_PENDING_TTL_MS = 10 * 60 * 1000;
const EMAIL_CODE_RESEND_MS = 60 * 1000;

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type MaybeRecord = Record<string, unknown>;
type PendingEmailCodeSession = {
  email: string;
  expiresAt: number;
  cooldownUntil: number;
};
type TelegramLoginTimeout = {
  signal: AbortSignal;
  promise: Promise<unknown>;
  clear(): void;
  timedOut: boolean;
};
type TelegramSdk = {
  hasLaunchParams(): boolean;
  createMiniAppAuthTimeout(): TelegramLoginTimeout;
  ensureForAction(): Promise<unknown>;
};
type AuthStoreDeps = {
  publicApi: ApiClient["publicApi"];
  setToken: (token: string, csrfToken?: string) => void;
  loadData: (options?: LoadDataOptions) => Promise<unknown>;
  telegramSdk: TelegramSdk;
  getTg: () => unknown;
  t: Translate;
  currentLang: () => string;
};
export type AuthState = {
  authStatus: string;
  authIsError: boolean;
  authBusy: boolean;
  telegramLoginBusy: boolean;
  telegramLoginAttemptId: number;
  loginEmailFieldError: string;
  loginEmailTooltipOpen: boolean;
  authResendCooldown: number;
  email: string;
  emailPassword: string;
  pendingEmail: string;
  emailCode: string;
  passwordLoginMode: boolean;
  passwordLoginFallback: boolean;
};
export type AuthStore = AuthState & {
  update(updater: (snapshot: AuthState) => AuthState): void;
  finalizeMagicLogin(loginToken: string): Promise<boolean>;
  finalizeTelegramAuth(
    authData: unknown,
    source?: "auth_data" | "init_data" | "id_token",
    options?: { signal?: AbortSignal }
  ): Promise<boolean>;
  requestEmailCode(changeScreen: (screen: string) => void): Promise<void>;
  loginWithEmailPassword(): Promise<void>;
  verifyEmailCode(): Promise<void>;
  openTelegramLogin(
    telegramOAuthClientId: number | string | null,
    getTelegramMiniAppInitData: () => string
  ): Promise<void>;
  restorePendingEmailCode(changeScreen?: (screen: string) => void): boolean;
  clearPendingEmailCode(): void;
  clearCooldownTimer(): void;
  stopTelegramLoginWatchdog(attemptId?: number | null): void;
  setAuthStatus(message: string, isError?: boolean): void;
};

function asRecord(value: unknown): MaybeRecord {
  return value && typeof value === "object" ? (value as MaybeRecord) : {};
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function setSessionFromAuthResponse(
  response: { token?: unknown; csrf_token?: unknown },
  setToken: (token: string, csrfToken?: string) => void
): boolean {
  const csrfToken = stringField(response.csrf_token);
  if (!csrfToken) return false;
  setToken(stringField(response.token), csrfToken);
  return true;
}

const buildTelegramOAuthUrl = buildTelegramOAuthStartUrl as (
  purpose?: string,
  tg?: unknown
) => string;

export function createAuthStore({
  publicApi,
  setToken,
  loadData,
  telegramSdk,
  getTg,
  t,
  currentLang,
}: AuthStoreDeps) {
  const state = $state<AuthStore>({
    authStatus: "",
    authIsError: false,
    authBusy: false,
    telegramLoginBusy: false,
    telegramLoginAttemptId: 0,
    loginEmailFieldError: "",
    loginEmailTooltipOpen: false,
    authResendCooldown: 0,
    email: "",
    emailPassword: "",
    pendingEmail: "",
    emailCode: "",
    passwordLoginMode: false,
    passwordLoginFallback: false,
    update: updateState,
    finalizeMagicLogin,
    finalizeTelegramAuth,
    requestEmailCode,
    loginWithEmailPassword,
    verifyEmailCode,
    openTelegramLogin,
    restorePendingEmailCode,
    clearPendingEmailCode,
    clearCooldownTimer,
    stopTelegramLoginWatchdog,
    setAuthStatus,
  });

  function updateState(updater: (snapshot: AuthState) => AuthState): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  let authResendTimer: number | null = null;
  let telegramLoginWatchdogTimer: number | null = null;

  function readPendingEmailCodeSession(): PendingEmailCodeSession | null {
    if (typeof window === "undefined" || !window.sessionStorage) return null;
    try {
      const raw = window.sessionStorage.getItem(EMAIL_CODE_PENDING_STORAGE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      const email = String(parsed?.email || "")
        .trim()
        .toLowerCase();
      const expiresAt = Number(parsed?.expiresAt || 0);
      const cooldownUntil = Number(parsed?.cooldownUntil || 0);
      if (!email || !email.includes("@") || !expiresAt || expiresAt <= Date.now()) {
        window.sessionStorage.removeItem(EMAIL_CODE_PENDING_STORAGE_KEY);
        return null;
      }
      return { email, expiresAt, cooldownUntil };
    } catch (_error) {
      window.sessionStorage.removeItem(EMAIL_CODE_PENDING_STORAGE_KEY);
      return null;
    }
  }

  function writePendingEmailCodeSession(email: string) {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    try {
      window.sessionStorage.setItem(
        EMAIL_CODE_PENDING_STORAGE_KEY,
        JSON.stringify({
          email,
          expiresAt: Date.now() + EMAIL_CODE_PENDING_TTL_MS,
          cooldownUntil: Date.now() + EMAIL_CODE_RESEND_MS,
        })
      );
    } catch (_error) {
      void _error;
    }
  }

  function clearPendingEmailCode() {
    if (typeof window === "undefined" || !window.sessionStorage) return;
    try {
      window.sessionStorage.removeItem(EMAIL_CODE_PENDING_STORAGE_KEY);
    } catch (_error) {
      void _error;
    }
  }

  function restorePendingEmailCode(changeScreen?: (screen: string) => void) {
    const pending = readPendingEmailCodeSession();
    if (!pending) return false;
    updateState((s) => ({
      ...s,
      email: pending.email,
      pendingEmail: pending.email,
      emailCode: "",
      authStatus: "",
      authIsError: false,
      authBusy: false,
      passwordLoginMode: false,
      passwordLoginFallback: false,
      loginEmailFieldError: "",
      loginEmailTooltipOpen: false,
    }));
    const cooldownSeconds = Math.ceil((pending.cooldownUntil - Date.now()) / 1000);
    if (cooldownSeconds > 0) {
      startCooldownTimer(cooldownSeconds);
    } else {
      clearCooldownTimer();
      updateState((s) => ({ ...s, authResendCooldown: 0 }));
    }
    if (typeof changeScreen === "function") changeScreen("code");
    return true;
  }

  function setAuthStatus(message: string, isError = false) {
    updateState((s) => ({ ...s, authStatus: message, authIsError: isError }));
  }

  function clearCooldownTimer() {
    if (authResendTimer) {
      window.clearInterval(authResendTimer);
      authResendTimer = null;
    }
  }

  function startCooldownTimer(seconds = 60) {
    clearCooldownTimer();
    updateState((s) => ({ ...s, authResendCooldown: Math.max(0, Number(seconds || 60)) }));
    authResendTimer = window.setInterval(() => {
      const { authResendCooldown } = state;
      if (authResendCooldown <= 1) {
        updateState((s) => ({ ...s, authResendCooldown: 0 }));
        clearCooldownTimer();
        return;
      }
      updateState((s) => ({ ...s, authResendCooldown: authResendCooldown - 1 }));
    }, 1000);
  }

  function startTelegramLoginWatchdog() {
    const TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS = 6000;
    stopTelegramLoginWatchdog();
    updateState((s) => ({ ...s, telegramLoginAttemptId: s.telegramLoginAttemptId + 1 }));
    const { telegramLoginAttemptId } = state;

    telegramLoginWatchdogTimer = window.setTimeout(() => {
      if (state.telegramLoginAttemptId !== telegramLoginAttemptId) return;
      telegramLoginWatchdogTimer = null;
      updateState((s) => ({ ...s, telegramLoginBusy: false, authBusy: false }));
      setAuthStatus(t("wa_auth_telegram_timeout"), true);
    }, TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS);

    return telegramLoginAttemptId;
  }

  function stopTelegramLoginWatchdog(attemptId: number | null = null) {
    if (attemptId !== null && attemptId !== state.telegramLoginAttemptId) return;
    if (telegramLoginWatchdogTimer) {
      window.clearTimeout(telegramLoginWatchdogTimer);
      telegramLoginWatchdogTimer = null;
    }
  }

  function isActiveTelegramLoginAttempt(attemptId: number) {
    const s = state;
    return attemptId === s.telegramLoginAttemptId && s.telegramLoginBusy;
  }

  async function finalizeMagicLogin(loginToken: string) {
    const s = state;
    if (s.authBusy) return false;
    updateState((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_login"));
    try {
      const payload: Record<string, unknown> = { token: loginToken };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi(
        buildAuthEmailMagicPath(),
        payload as PostPayload<"/api/auth/email/magic">
      );
      if (response.ok) {
        const responsePayload = unwrap(response);
        if (!setSessionFromAuthResponse(responsePayload, setToken)) {
          setAuthStatus(t("wa_auth_login_confirm_failed"), true);
          return false;
        }
        clearPendingEmailCode();
        clearAuthQuery();
        await loadData();
        return true;
      }
      const errorCode = stringField(asRecord(response).error);
      setAuthStatus(
        errorCode === "registration_invite_required"
          ? t("wa_auth_invite_required")
          : t("wa_auth_login_confirm_failed"),
        true
      );
    } catch {
      setAuthStatus(t("wa_auth_login_confirm_failed"), true);
    } finally {
      updateState((s) => ({ ...s, authBusy: false }));
    }
    return false;
  }

  async function finalizeTelegramAuth(
    authData: unknown,
    source: "auth_data" | "init_data" | "id_token" = "auth_data",
    options: { signal?: AbortSignal } = {}
  ) {
    const s = state;
    if (s.authBusy) return false;
    updateState((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_telegram"));
    try {
      const authRecord = asRecord(authData);
      const payload: Record<string, unknown> =
        source === "init_data"
          ? { init_data: authData }
          : source === "id_token"
            ? { id_token: authRecord.id_token, nonce: authRecord.nonce }
            : { auth_data: authData };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi(
        buildAuthTokenPath(),
        payload as PostPayload<"/api/auth/token">,
        {
          signal: options.signal,
        }
      );
      if (response.ok) {
        const responsePayload = unwrap(response);
        if (!setSessionFromAuthResponse(responsePayload, setToken)) {
          setAuthStatus(t("wa_auth_telegram_not_confirmed"), true);
          return false;
        }
        clearPendingEmailCode();
        clearAuthQuery();
        setAuthStatus("");
        await loadData();
        return true;
      }
      const errorCode = stringField(asRecord(response).error);
      setAuthStatus(
        errorCode === "banned"
          ? t("wa_auth_access_denied")
          : errorCode === "registration_invite_required"
            ? t("wa_auth_invite_required")
            : t("wa_auth_telegram_not_confirmed"),
        true
      );
    } catch (error) {
      const errorName = stringField(asRecord(error).name);
      setAuthStatus(
        errorName === "AbortError"
          ? t("wa_auth_telegram_timeout")
          : t("wa_auth_telegram_unavailable"),
        true
      );
    } finally {
      updateState((s) => ({ ...s, authBusy: false }));
    }
    return false;
  }

  async function requestEmailCode(changeScreen: (screen: string) => void) {
    const s = state;
    const normalized = s.email.trim().toLowerCase();
    if (
      s.authResendCooldown > 0 &&
      s.pendingEmail &&
      (!normalized || normalized === s.pendingEmail)
    ) {
      if (typeof changeScreen === "function") changeScreen("code");
      return;
    }
    if (!normalized || !normalized.includes("@")) {
      updateState((s) => ({
        ...s,
        loginEmailFieldError: t("wa_auth_invalid_email"),
        loginEmailTooltipOpen: true,
      }));
      return;
    }
    updateState((s) => ({
      ...s,
      loginEmailFieldError: "",
      loginEmailTooltipOpen: false,
      authBusy: true,
      passwordLoginFallback: false,
    }));
    setAuthStatus(t("wa_auth_sending_code"));
    try {
      const payload: Record<string, unknown> = { email: normalized, language: currentLang() };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi(
        buildAuthEmailRequestPath(),
        payload as PostPayload<"/api/auth/email/request">
      );
      if (!response.ok) throw response;
      const responsePayload = unwrap(response);
      const presetCode = String(responsePayload.email_code || responsePayload.code || "")
        .replace(/\D/g, "")
        .slice(0, 6);
      updateState((s) => ({ ...s, pendingEmail: normalized, emailCode: presetCode }));
      writePendingEmailCodeSession(normalized);
      changeScreen("code");
      setAuthStatus("");
      startCooldownTimer(60);
    } catch (error: unknown) {
      setAuthStatus(emailError(error, t("wa_auth_send_code_failed"), t), true);
    } finally {
      updateState((s) => ({ ...s, authBusy: false }));
    }
  }

  async function loginWithEmailPassword() {
    const s = state;
    const normalized = s.email.trim().toLowerCase();
    const password = String(s.emailPassword || "");
    if (!normalized || !normalized.includes("@")) {
      updateState((s) => ({
        ...s,
        loginEmailFieldError: t("wa_auth_invalid_email"),
        loginEmailTooltipOpen: true,
      }));
      return;
    }
    if (!password) {
      setAuthStatus(t("wa_auth_password_required"), true);
      return;
    }
    updateState((s) => ({
      ...s,
      loginEmailFieldError: "",
      loginEmailTooltipOpen: false,
      authBusy: true,
      passwordLoginFallback: false,
    }));
    setAuthStatus(t("wa_auth_checking_password"));
    try {
      const response = await publicApi(buildAuthEmailPasswordPath(), {
        email: normalized,
        password,
      } as PostPayload<"/api/auth/email/password">);
      if (!response.ok) throw response;
      const responsePayload = unwrap(response);
      if (!setSessionFromAuthResponse(responsePayload, setToken)) throw response;
      clearPendingEmailCode();
      await loadData();
      setAuthStatus("");
    } catch (error: unknown) {
      const errorCode = stringField(asRecord(error).error);
      if (errorCode === "rate_limited") {
        setAuthStatus(emailError(error, t("wa_auth_password_login_failed"), t), true);
      } else if (errorCode === "banned") {
        setAuthStatus(t("wa_auth_access_denied"), true);
      } else {
        updateState((s) => ({ ...s, passwordLoginFallback: true }));
        setAuthStatus(t("wa_auth_password_login_failed"), true);
      }
    } finally {
      updateState((s) => ({ ...s, authBusy: false }));
    }
  }

  async function verifyEmailCode() {
    const s = state;
    const code = s.emailCode.replace(/\\D/g, "").slice(0, 6);
    if (code.length !== 6) {
      setAuthStatus(t("wa_auth_enter_code_6digits"), true);
      return;
    }
    updateState((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_code"));
    try {
      const payload: Record<string, unknown> = { email: s.pendingEmail, code };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi(
        buildAuthEmailVerifyPath(),
        payload as PostPayload<"/api/auth/email/verify">
      );
      if (!response.ok) throw response;
      const responsePayload = unwrap(response);
      if (!setSessionFromAuthResponse(responsePayload, setToken)) throw response;
      clearPendingEmailCode();
      await loadData();
      setAuthStatus("");
    } catch (error: unknown) {
      setAuthStatus(emailError(error, t("wa_auth_invalid_code"), t), true);
    } finally {
      updateState((s) => ({ ...s, authBusy: false }));
    }
  }

  async function openTelegramLogin(
    telegramOAuthClientId: number | string | null,
    getTelegramMiniAppInitData: () => string
  ) {
    const s = state;
    if (s.authBusy || s.telegramLoginBusy) return;
    setAuthStatus("");

    const isTelegramMiniAppAttempt = telegramSdk.hasLaunchParams();
    if (!isTelegramMiniAppAttempt && telegramOAuthClientId) {
      updateState((s) => ({ ...s, telegramLoginBusy: true }));
      window.location.assign(buildTelegramOAuthUrl("login", getTg()));
      window.setTimeout(() => {
        updateState((s) => ({ ...s, telegramLoginBusy: false }));
      }, 1500);
      return;
    }

    updateState((s) => ({ ...s, telegramLoginBusy: true }));
    const attemptId = startTelegramLoginWatchdog();
    const loginTimeout = telegramSdk.createMiniAppAuthTimeout();
    try {
      await Promise.race([
        (async () => {
          await telegramSdk.ensureForAction();
          if (!isActiveTelegramLoginAttempt(attemptId)) return;
          const initData = getTelegramMiniAppInitData();
          if (initData) {
            await finalizeTelegramAuth(initData, "init_data", { signal: loginTimeout.signal });
            return;
          }

          if (!telegramOAuthClientId) {
            setAuthStatus(t("wa_auth_telegram_not_configured"), true);
            return;
          }

          window.location.assign(buildTelegramOAuthUrl("login", getTg()));
        })(),
        loginTimeout.promise,
      ]);
    } catch (error: unknown) {
      if (!isActiveTelegramLoginAttempt(attemptId)) return;
      if (stringField(asRecord(error).name) === "AbortError") {
        setAuthStatus(t("wa_auth_telegram_timeout"), true);
      } else {
        setAuthStatus(t("wa_auth_telegram_unavailable"), true);
      }
    } finally {
      loginTimeout.clear();
      if (loginTimeout.timedOut) {
        setAuthStatus(t("wa_auth_telegram_timeout"), true);
        updateState((s) => ({ ...s, authBusy: false }));
      }
      if (isActiveTelegramLoginAttempt(attemptId)) {
        stopTelegramLoginWatchdog(attemptId);
        updateState((s) => ({ ...s, telegramLoginBusy: false }));
      }
    }
  }

  return state;
}
