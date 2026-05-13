import { writable, get } from "svelte/store";
import { emailError, buildTelegramOAuthStartUrl } from "../authHelpers.js";

export function createAccountStore({
  api,
  publicApi,
  setToken,
  loadData,
  t,
  showToast,
  clearToken,
  markManualLogout,
  showLogin,
  telegramSdk,
  getTg,
  telegramOAuthClientId,
  currentLang,
  normalizeLangCode,
  updateLocalData,
}) {
  const state = writable({
    linkEmailOpen: false,
    linkEmailBusy: false,
    linkTelegramBusy: false,
    linkEmailValue: "",
    linkEmailPending: "",
    linkEmailCode: "",
    linkEmailStatus: "",
    linkEmailIsError: false,
    linkEmailFieldError: "",
    linkEmailResendCooldown: 0,
    languageBusy: false,
  });

  let linkEmailResendTimer = null;

  function setLinkEmailStatus(message, isError = false) {
    state.update((s) => ({ ...s, linkEmailStatus: message, linkEmailIsError: isError }));
  }

  function clearCooldownTimer() {
    if (linkEmailResendTimer) {
      window.clearInterval(linkEmailResendTimer);
      linkEmailResendTimer = null;
    }
  }

  function startCooldownTimer(seconds = 60) {
    clearCooldownTimer();
    state.update((s) => ({ ...s, linkEmailResendCooldown: Math.max(0, Number(seconds || 60)) }));
    linkEmailResendTimer = window.setInterval(() => {
      const s = get(state);
      if (s.linkEmailResendCooldown <= 1) {
        state.update((s) => ({ ...s, linkEmailResendCooldown: 0 }));
        clearCooldownTimer();
        return;
      }
      state.update((s) => ({ ...s, linkEmailResendCooldown: s.linkEmailResendCooldown - 1 }));
    }, 1000);
  }

  function openLinkEmailDialog(email) {
    state.update((s) => ({
      ...s,
      linkEmailOpen: true,
      linkEmailBusy: false,
      linkEmailCode: "",
      linkEmailPending: "",
      linkEmailStatus: "",
      linkEmailIsError: false,
      linkEmailFieldError: "",
      linkEmailValue: email || "",
      linkEmailResendCooldown: 0,
    }));
    clearCooldownTimer();
  }

  function closeLinkEmailDialog() {
    state.update((s) => ({
      ...s,
      linkEmailOpen: false,
      linkEmailBusy: false,
      linkEmailCode: "",
      linkEmailPending: "",
      linkEmailStatus: "",
      linkEmailIsError: false,
      linkEmailFieldError: "",
      linkEmailResendCooldown: 0,
    }));
    clearCooldownTimer();
  }

  async function requestLinkEmailCode() {
    const s = get(state);
    if (s.linkEmailPending && s.linkEmailResendCooldown > 0) return;
    const normalized = String(s.linkEmailValue || "")
      .trim()
      .toLowerCase();
    if (!normalized || !normalized.includes("@")) {
      state.update((s) => ({ ...s, linkEmailFieldError: t("wa_auth_invalid_email") }));
      return;
    }
    state.update((s) => ({ ...s, linkEmailFieldError: "", linkEmailBusy: true }));
    setLinkEmailStatus(t("wa_auth_sending_code"));
    try {
      const response = await api("/account/email/request", {
        method: "POST",
        body: JSON.stringify({ email: normalized }),
      });
      if (!response?.ok) throw response;
      state.update((s) => ({ ...s, linkEmailPending: normalized, linkEmailCode: "" }));
      setLinkEmailStatus("");
      startCooldownTimer(60);
    } catch (error) {
      setLinkEmailStatus(emailError(error, t("wa_auth_send_code_failed"), t), true);
    } finally {
      state.update((s) => ({ ...s, linkEmailBusy: false }));
    }
  }

  async function verifyLinkEmailCode() {
    const s = get(state);
    const code = String(s.linkEmailCode || "")
      .replace(/\\D/g, "")
      .slice(0, 6);
    if (!s.linkEmailPending) {
      setLinkEmailStatus(t("wa_auth_send_code_failed"), true);
      return;
    }
    if (code.length !== 6) {
      setLinkEmailStatus(t("wa_auth_enter_code_6digits"), true);
      return;
    }
    state.update((s) => ({ ...s, linkEmailBusy: true }));
    setLinkEmailStatus(t("wa_auth_checking_code"));
    try {
      const response = await api("/account/email/verify", {
        method: "POST",
        body: JSON.stringify({ email: s.linkEmailPending, code }),
      });
      if (!response?.ok) throw response;
      if (response?.token) setToken(response.token, response.csrf_token);
      await loadData();
      closeLinkEmailDialog();
      showToast(t("wa_settings_linked"));
    } catch (error) {
      setLinkEmailStatus(emailError(error, t("wa_auth_invalid_code"), t), true);
    } finally {
      state.update((s) => ({ ...s, linkEmailBusy: false }));
    }
  }

  async function linkTelegramAccountWithPayload(payload) {
    state.update((s) => ({ ...s, linkTelegramBusy: true }));
    try {
      const response = await api("/account/telegram/link", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      if (response?.token) setToken(response.token, response.csrf_token);
      await loadData();
      showToast(t("wa_settings_linked"));
    } catch (error) {
      showToast(error?.message || t("wa_auth_telegram_not_confirmed"));
    } finally {
      state.update((s) => ({ ...s, linkTelegramBusy: false }));
    }
  }

  async function linkTelegramAccount(getTelegramMiniAppInitData) {
    const s = get(state);
    if (s.linkTelegramBusy) return;
    const isTelegramMiniAppAttempt = telegramSdk.hasLaunchParams();
    if (isTelegramMiniAppAttempt) {
      await telegramSdk.ensureForAction();
    }
    const initData = getTelegramMiniAppInitData();
    if (initData) {
      await linkTelegramAccountWithPayload({ init_data: initData });
      return;
    }
    if (!telegramOAuthClientId) {
      showToast(t("wa_auth_telegram_not_configured"));
      return;
    }
    state.update((s) => ({ ...s, linkTelegramBusy: true }));
    window.location.assign(buildTelegramOAuthStartUrl("link", getTg()));
  }

  async function updateAccountLanguage(nextValue) {
    const s = get(state);
    const normalize = typeof normalizeLangCode === "function" ? normalizeLangCode : (v) => v;
    const language = normalize(nextValue);
    if (!language || s.languageBusy || language === currentLang()) return;
    state.update((s) => ({ ...s, languageBusy: true }));
    try {
      const response = await api("/account/language", {
        method: "POST",
        body: JSON.stringify({ language }),
      });
      if (!response?.ok) throw response;
      if (typeof updateLocalData === "function") {
        updateLocalData(normalize(response.language || language));
      }
      await loadData();
    } catch {
      showToast(t("wa_settings_language_update_failed"));
    } finally {
      state.update((s) => ({ ...s, languageBusy: false }));
    }
  }

  async function logout() {
    markManualLogout();
    clearToken();
    try {
      await publicApi("/auth/logout", { keepalive: true });
    } catch (_error) {
      void _error;
    }
    showLogin();
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    openLinkEmailDialog,
    closeLinkEmailDialog,
    requestLinkEmailCode,
    verifyLinkEmailCode,
    linkTelegramAccount,
    updateAccountLanguage,
    logout,
    clearLinkEmailResendTimer: clearCooldownTimer,
  };
}
