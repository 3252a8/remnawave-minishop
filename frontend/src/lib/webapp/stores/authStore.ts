import { writable, get } from "svelte/store";
import {
  readReferralParam,
  clearAuthQuery,
  buildTelegramOAuthStartUrl,
  emailError,
} from "../authHelpers.js";
import type { LoadDataOptions } from "../dataClient";
import type { ApiClient, PostPayload } from "../publicApi";
import { unwrap } from "../publicApi";

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

function asRecord(value: unknown): MaybeRecord {
  return value && typeof value === "object" ? (value as MaybeRecord) : {};
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
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
  const state = writable<AuthState>({
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
  });

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
    state.update((s) => ({
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
      state.update((s) => ({ ...s, authResendCooldown: 0 }));
    }
    if (typeof changeScreen === "function") changeScreen("code");
    return true;
  }

  function setAuthStatus(message: string, isError = false) {
    state.update((s) => ({ ...s, authStatus: message, authIsError: isError }));
  }

  function clearCooldownTimer() {
    if (authResendTimer) {
      window.clearInterval(authResendTimer);
      authResendTimer = null;
    }
  }

  function startCooldownTimer(seconds = 60) {
    clearCooldownTimer();
    state.update((s) => ({ ...s, authResendCooldown: Math.max(0, Number(seconds || 60)) }));
    authResendTimer = window.setInterval(() => {
      const { authResendCooldown } = get(state);
      if (authResendCooldown <= 1) {
        state.update((s) => ({ ...s, authResendCooldown: 0 }));
        clearCooldownTimer();
        return;
      }
      state.update((s) => ({ ...s, authResendCooldown: authResendCooldown - 1 }));
    }, 1000);
  }

  function startTelegramLoginWatchdog() {
    const TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS = 6000;
    stopTelegramLoginWatchdog();
    state.update((s) => ({ ...s, telegramLoginAttemptId: s.telegramLoginAttemptId + 1 }));
    const { telegramLoginAttemptId } = get(state);

    telegramLoginWatchdogTimer = window.setTimeout(() => {
      if (get(state).telegramLoginAttemptId !== telegramLoginAttemptId) return;
      telegramLoginWatchdogTimer = null;
      state.update((s) => ({ ...s, telegramLoginBusy: false, authBusy: false }));
      setAuthStatus(t("wa_auth_telegram_timeout"), true);
    }, TELEGRAM_MINI_APP_AUTH_TIMEOUT_MS);

    return telegramLoginAttemptId;
  }

  function stopTelegramLoginWatchdog(attemptId: number | null = null) {
    if (attemptId !== null && attemptId !== get(state).telegramLoginAttemptId) return;
    if (telegramLoginWatchdogTimer) {
      window.clearTimeout(telegramLoginWatchdogTimer);
      telegramLoginWatchdogTimer = null;
    }
  }

  function isActiveTelegramLoginAttempt(attemptId: number) {
    const s = get(state);
    return attemptId === s.telegramLoginAttemptId && s.telegramLoginBusy;
  }

  async function finalizeMagicLogin(loginToken: string) {
    const s = get(state);
    if (s.authBusy) return false;
    state.update((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_login"));
    try {
      const payload: Record<string, unknown> = { token: loginToken };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi(
        "/auth/email/magic",
        payload as PostPayload<"/api/auth/email/magic">
      );
      if (response.ok) {
        const csrfToken = stringField(unwrap(response).csrf_token);
        if (!csrfToken) {
          setAuthStatus(t("wa_auth_login_confirm_failed"), true);
          return false;
        }
        setToken("", csrfToken);
        clearPendingEmailCode();
        clearAuthQuery();
        await loadData();
        return true;
      }
      setAuthStatus(t("wa_auth_login_confirm_failed"), true);
    } catch {
      setAuthStatus(t("wa_auth_login_confirm_failed"), true);
    } finally {
      state.update((s) => ({ ...s, authBusy: false }));
    }
    return false;
  }

  async function finalizeTelegramAuth(
    authData: unknown,
    source: "auth_data" | "init_data" | "id_token" = "auth_data",
    options: { signal?: AbortSignal } = {}
  ) {
    const s = get(state);
    if (s.authBusy) return false;
    state.update((s) => ({ ...s, authBusy: true }));
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
      const response = await publicApi("/auth/token", payload as PostPayload<"/api/auth/token">, {
        signal: options.signal,
      });
      if (response.ok) {
        const csrfToken = stringField(unwrap(response).csrf_token);
        if (!csrfToken) {
          setAuthStatus(t("wa_auth_telegram_not_confirmed"), true);
          return false;
        }
        setToken("", csrfToken);
        clearPendingEmailCode();
        clearAuthQuery();
        setAuthStatus("");
        await loadData();
        return true;
      }
      const errorCode = stringField(asRecord(response).error);
      setAuthStatus(
        errorCode === "banned" ? t("wa_auth_access_denied") : t("wa_auth_telegram_not_confirmed"),
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
      state.update((s) => ({ ...s, authBusy: false }));
    }
    return false;
  }

  async function requestEmailCode(changeScreen: (screen: string) => void) {
    const s = get(state);
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
      state.update((s) => ({
        ...s,
        loginEmailFieldError: t("wa_auth_invalid_email"),
        loginEmailTooltipOpen: true,
      }));
      return;
    }
    state.update((s) => ({
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
        "/auth/email/request",
        payload as PostPayload<"/api/auth/email/request">
      );
      if (!response.ok) throw response;
      const responsePayload = unwrap(response);
      const presetCode = String(responsePayload.email_code || responsePayload.code || "")
        .replace(/\D/g, "")
        .slice(0, 6);
      state.update((s) => ({ ...s, pendingEmail: normalized, emailCode: presetCode }));
      writePendingEmailCodeSession(normalized);
      changeScreen("code");
      setAuthStatus("");
      startCooldownTimer(60);
    } catch (error: unknown) {
      setAuthStatus(emailError(error, t("wa_auth_send_code_failed"), t), true);
    } finally {
      state.update((s) => ({ ...s, authBusy: false }));
    }
  }

  async function loginWithEmailPassword() {
    const s = get(state);
    const normalized = s.email.trim().toLowerCase();
    const password = String(s.emailPassword || "");
    if (!normalized || !normalized.includes("@")) {
      state.update((s) => ({
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
    state.update((s) => ({
      ...s,
      loginEmailFieldError: "",
      loginEmailTooltipOpen: false,
      authBusy: true,
      passwordLoginFallback: false,
    }));
    setAuthStatus(t("wa_auth_checking_password"));
    try {
      const response = await publicApi("/auth/email/password", {
        email: normalized,
        password,
      } as PostPayload<"/api/auth/email/password">);
      if (!response.ok) throw response;
      const csrfToken = stringField(unwrap(response).csrf_token);
      if (!csrfToken) throw response;
      setToken("", csrfToken);
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
        state.update((s) => ({ ...s, passwordLoginFallback: true }));
        setAuthStatus(t("wa_auth_password_login_failed"), true);
      }
    } finally {
      state.update((s) => ({ ...s, authBusy: false }));
    }
  }

  async function verifyEmailCode() {
    const s = get(state);
    const code = s.emailCode.replace(/\\D/g, "").slice(0, 6);
    if (code.length !== 6) {
      setAuthStatus(t("wa_auth_enter_code_6digits"), true);
      return;
    }
    state.update((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_code"));
    try {
      const payload: Record<string, unknown> = { email: s.pendingEmail, code };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi(
        "/auth/email/verify",
        payload as PostPayload<"/api/auth/email/verify">
      );
      if (!response.ok) throw response;
      const csrfToken = stringField(unwrap(response).csrf_token);
      if (!csrfToken) throw response;
      setToken("", csrfToken);
      clearPendingEmailCode();
      await loadData();
      setAuthStatus("");
    } catch (error: unknown) {
      setAuthStatus(emailError(error, t("wa_auth_invalid_code"), t), true);
    } finally {
      state.update((s) => ({ ...s, authBusy: false }));
    }
  }

  async function openTelegramLogin(
    telegramOAuthClientId: number | string | null,
    getTelegramMiniAppInitData: () => string
  ) {
    const s = get(state);
    if (s.authBusy || s.telegramLoginBusy) return;
    setAuthStatus("");

    const isTelegramMiniAppAttempt = telegramSdk.hasLaunchParams();
    if (!isTelegramMiniAppAttempt && telegramOAuthClientId) {
      state.update((s) => ({ ...s, telegramLoginBusy: true }));
      window.location.assign(buildTelegramOAuthUrl("login", getTg()));
      window.setTimeout(() => {
        state.update((s) => ({ ...s, telegramLoginBusy: false }));
      }, 1500);
      return;
    }

    state.update((s) => ({ ...s, telegramLoginBusy: true }));
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
        state.update((s) => ({ ...s, authBusy: false }));
      }
      if (isActiveTelegramLoginAttempt(attemptId)) {
        stopTelegramLoginWatchdog(attemptId);
        state.update((s) => ({ ...s, telegramLoginBusy: false }));
      }
    }
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
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
  };
}
