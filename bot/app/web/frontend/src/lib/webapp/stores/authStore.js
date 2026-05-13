import { writable, get } from "svelte/store";
import {
  readReferralParam,
  clearAuthQuery,
  buildTelegramOAuthStartUrl,
  emailError,
} from "../authHelpers.js";

export function createAuthStore({
  publicApi,
  setToken,
  loadData,
  telegramSdk,
  getTg,
  t,
  currentLang,
}) {
  const state = writable({
    authStatus: "",
    authIsError: false,
    authBusy: false,
    telegramLoginBusy: false,
    telegramLoginAttemptId: 0,
    loginEmailFieldError: "",
    loginEmailTooltipOpen: false,
    authResendCooldown: 0,
    email: "",
    pendingEmail: "",
    emailCode: "",
  });

  let authResendTimer = null;
  let telegramLoginWatchdogTimer = null;

  function setAuthStatus(message, isError = false) {
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

  function stopTelegramLoginWatchdog(attemptId = null) {
    if (attemptId !== null && attemptId !== get(state).telegramLoginAttemptId) return;
    if (telegramLoginWatchdogTimer) {
      window.clearTimeout(telegramLoginWatchdogTimer);
      telegramLoginWatchdogTimer = null;
    }
  }

  function isActiveTelegramLoginAttempt(attemptId) {
    const s = get(state);
    return attemptId === s.telegramLoginAttemptId && s.telegramLoginBusy;
  }

  async function finalizeMagicLogin(loginToken) {
    const s = get(state);
    if (s.authBusy) return false;
    state.update((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_login"));
    try {
      const payload = { token: loginToken };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/magic", payload);
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
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

  async function finalizeTelegramAuth(authData, source = "auth_data", options = {}) {
    const s = get(state);
    if (s.authBusy) return false;
    state.update((s) => ({ ...s, authBusy: true }));
    setAuthStatus(t("wa_auth_checking_telegram"));
    try {
      const payload =
        source === "init_data"
          ? { init_data: authData }
          : source === "id_token"
            ? { id_token: authData.id_token, nonce: authData.nonce }
            : { auth_data: authData };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/token", payload, { signal: options.signal });
      if (response.ok && response.token) {
        setToken(response.token, response.csrf_token);
        clearAuthQuery();
        setAuthStatus("");
        await loadData();
        return true;
      }
      setAuthStatus(
        response.error === "banned"
          ? t("wa_auth_access_denied")
          : t("wa_auth_telegram_not_confirmed"),
        true
      );
    } catch (error) {
      setAuthStatus(
        error?.name === "AbortError"
          ? t("wa_auth_telegram_timeout")
          : t("wa_auth_telegram_unavailable"),
        true
      );
    } finally {
      state.update((s) => ({ ...s, authBusy: false }));
    }
    return false;
  }

  async function requestEmailCode(changeScreen) {
    const s = get(state);
    if (s.authResendCooldown > 0 && s.pendingEmail) return;
    const normalized = s.email.trim().toLowerCase();
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
    }));
    setAuthStatus(t("wa_auth_sending_code"));
    try {
      const payload = { email: normalized, language: currentLang() };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/request", payload);
      if (!response.ok) throw response;
      state.update((s) => ({ ...s, pendingEmail: normalized, emailCode: "" }));
      changeScreen("code");
      setAuthStatus("");
      startCooldownTimer(60);
    } catch (error) {
      setAuthStatus(emailError(error, t("wa_auth_send_code_failed"), t), true);
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
      const payload = { email: s.pendingEmail, code };
      const referralParam = readReferralParam(getTg());
      if (referralParam) payload.referral_code = referralParam;
      const response = await publicApi("/auth/email/verify", payload);
      if (!response.ok || !response.token) throw response;
      setToken(response.token, response.csrf_token);
      await loadData();
      setAuthStatus("");
    } catch (error) {
      setAuthStatus(emailError(error, t("wa_auth_invalid_code"), t), true);
    } finally {
      state.update((s) => ({ ...s, authBusy: false }));
    }
  }

  async function openTelegramLogin(telegramOAuthClientId, getTelegramMiniAppInitData) {
    const s = get(state);
    if (s.authBusy || s.telegramLoginBusy) return;
    setAuthStatus("");

    const isTelegramMiniAppAttempt = telegramSdk.hasLaunchParams();
    if (!isTelegramMiniAppAttempt && telegramOAuthClientId) {
      state.update((s) => ({ ...s, telegramLoginBusy: true }));
      window.location.assign(buildTelegramOAuthStartUrl("login", getTg()));
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

          window.location.assign(buildTelegramOAuthStartUrl("login", getTg()));
        })(),
        loginTimeout.promise,
      ]);
    } catch (error) {
      if (!isActiveTelegramLoginAttempt(attemptId)) return;
      if (error?.name === "AbortError") {
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
    verifyEmailCode,
    openTelegramLogin,
    clearCooldownTimer,
    stopTelegramLoginWatchdog,
    setAuthStatus,
  };
}
