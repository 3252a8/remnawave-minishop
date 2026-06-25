import { emailError, buildTelegramOAuthStartUrl } from "../authHelpers.js";
import type { LoadDataOptions } from "../dataClient";
import type { ApiClient, PostPayload } from "../publicApi";
import { unwrap } from "../publicApi";

const TELEGRAM_LINK_PENDING_ACTION_STORAGE_KEY = "rw_webapp_telegram_link_pending_action_v1";
const TELEGRAM_LINK_PENDING_TTL_MS = 10 * 60 * 1000;
const TELEGRAM_LINK_ACTION_TRIAL = "trial";
const TELEGRAM_LINK_ACTION_REFERRAL_WELCOME = "referral_welcome";

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TelegramSdk = {
  hasLaunchParams(): boolean;
  ensureForAction(): Promise<unknown>;
};
type TelegramLinkPendingAction =
  | typeof TELEGRAM_LINK_ACTION_TRIAL
  | typeof TELEGRAM_LINK_ACTION_REFERRAL_WELCOME;
type AccountStoreDeps = {
  api: ApiClient["api"];
  publicApi: ApiClient["publicApi"];
  setToken: (token: string, csrfToken?: string) => void;
  loadData: (options?: LoadDataOptions & Record<string, unknown>) => Promise<unknown>;
  t: Translate;
  showToast: (message: string) => void;
  clearToken: () => void;
  markManualLogout: () => void;
  showLogin: () => void;
  telegramSdk: TelegramSdk;
  getTg: () => unknown;
  getCurrentUser: () => unknown;
  getTelegramMiniAppInitData: () => string;
  isDemoAuthLogin: () => boolean;
  getDemoTelegramAuthPayload: () => unknown;
  telegramOAuthClientId: number | string | (() => number | string);
  currentLang: () => string;
  normalizeLangCode: (value: string) => string;
  updateLocalData: (updatedLanguage: string) => void;
  activateTrial: () => Promise<unknown>;
  claimReferralWelcomeBonus: () => Promise<unknown>;
};
export type AccountState = {
  linkEmailOpen: boolean;
  linkEmailBusy: boolean;
  linkTelegramBusy: boolean;
  linkEmailValue: string;
  linkEmailPending: string;
  linkEmailCode: string;
  linkEmailStatus: string;
  linkEmailIsError: boolean;
  linkEmailFieldError: string;
  linkEmailResendCooldown: number;
  setPasswordOpen: boolean;
  setPasswordBusy: boolean;
  setPasswordPending: boolean;
  setPasswordValue: string;
  setPasswordConfirm: string;
  setPasswordCode: string;
  setPasswordStatus: string;
  setPasswordIsError: boolean;
  setPasswordResendCooldown: number;
  languageBusy: boolean;
};
export type AccountStore = AccountState & {
  openLinkEmailDialog(email: string): void;
  closeLinkEmailDialog(): void;
  openSetPasswordDialog(): void;
  closeSetPasswordDialog(): void;
  requestLinkEmailCode(): Promise<void>;
  verifyLinkEmailCode(): Promise<void>;
  requestSetPasswordCode(): Promise<void>;
  confirmSetPassword(): Promise<void>;
  linkTelegramAccount(getTelegramMiniAppInitData?: () => string): Promise<void>;
  linkTelegramFromSettings(): Promise<void>;
  continueTelegramLinkPendingAction(): Promise<boolean>;
  linkTelegramAndActivateTrial(): Promise<void>;
  linkTelegramAndClaimReferralWelcome(): Promise<void>;
  updateAccountLanguage(nextValue: string, options?: Record<string, unknown>): Promise<void>;
  logout(): Promise<void>;
  clearLinkEmailResendTimer(): void;
  clearSetPasswordResendTimer(): void;
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

const buildTelegramOAuthUrl = buildTelegramOAuthStartUrl as (
  purpose?: string,
  tg?: unknown
) => string;

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
  getCurrentUser,
  getTelegramMiniAppInitData,
  isDemoAuthLogin,
  getDemoTelegramAuthPayload,
  telegramOAuthClientId,
  currentLang,
  normalizeLangCode,
  updateLocalData,
  activateTrial,
  claimReferralWelcomeBonus,
}: AccountStoreDeps) {
  const state = $state<AccountStore>({
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
    setPasswordOpen: false,
    setPasswordBusy: false,
    setPasswordPending: false,
    setPasswordValue: "",
    setPasswordConfirm: "",
    setPasswordCode: "",
    setPasswordStatus: "",
    setPasswordIsError: false,
    setPasswordResendCooldown: 0,
    languageBusy: false,
    openLinkEmailDialog,
    closeLinkEmailDialog,
    openSetPasswordDialog,
    closeSetPasswordDialog,
    requestLinkEmailCode,
    verifyLinkEmailCode,
    requestSetPasswordCode,
    confirmSetPassword,
    linkTelegramAccount,
    linkTelegramFromSettings,
    continueTelegramLinkPendingAction,
    linkTelegramAndActivateTrial,
    linkTelegramAndClaimReferralWelcome,
    updateAccountLanguage,
    logout,
    clearLinkEmailResendTimer: clearCooldownTimer,
    clearSetPasswordResendTimer: clearPasswordCooldownTimer,
  });

  function updateState(updater: (snapshot: AccountStore) => AccountStore): void {
    Object.assign(state, updater(state));
  }

  let linkEmailResendTimer: number | null = null;
  let setPasswordResendTimer: number | null = null;
  let telegramLinkPendingActionBusy = false;

  function setLinkEmailStatus(message: string, isError = false) {
    updateState((s) => ({ ...s, linkEmailStatus: message, linkEmailIsError: isError }));
  }

  function clearCooldownTimer() {
    if (linkEmailResendTimer) {
      window.clearInterval(linkEmailResendTimer);
      linkEmailResendTimer = null;
    }
  }

  function clearPasswordCooldownTimer() {
    if (setPasswordResendTimer) {
      window.clearInterval(setPasswordResendTimer);
      setPasswordResendTimer = null;
    }
  }

  function startCooldownTimer(seconds = 60) {
    clearCooldownTimer();
    updateState((s) => ({ ...s, linkEmailResendCooldown: Math.max(0, Number(seconds || 60)) }));
    linkEmailResendTimer = window.setInterval(() => {
      const s = state;
      if (s.linkEmailResendCooldown <= 1) {
        updateState((s) => ({ ...s, linkEmailResendCooldown: 0 }));
        clearCooldownTimer();
        return;
      }
      updateState((s) => ({ ...s, linkEmailResendCooldown: s.linkEmailResendCooldown - 1 }));
    }, 1000);
  }

  function startPasswordCooldownTimer(seconds = 60) {
    clearPasswordCooldownTimer();
    updateState((s) => ({ ...s, setPasswordResendCooldown: Math.max(0, Number(seconds || 60)) }));
    setPasswordResendTimer = window.setInterval(() => {
      const s = state;
      if (s.setPasswordResendCooldown <= 1) {
        updateState((s) => ({ ...s, setPasswordResendCooldown: 0 }));
        clearPasswordCooldownTimer();
        return;
      }
      updateState((s) => ({ ...s, setPasswordResendCooldown: s.setPasswordResendCooldown - 1 }));
    }, 1000);
  }

  function openLinkEmailDialog(email: string) {
    updateState((s) => ({
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
    updateState((s) => ({
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

  function setPasswordStatus(message: string, isError = false) {
    updateState((s) => ({
      ...s,
      setPasswordStatus: message,
      setPasswordIsError: isError,
    }));
  }

  function openSetPasswordDialog() {
    updateState((s) => ({
      ...s,
      setPasswordOpen: true,
      setPasswordBusy: false,
      setPasswordPending: false,
      setPasswordValue: "",
      setPasswordConfirm: "",
      setPasswordCode: "",
      setPasswordStatus: "",
      setPasswordIsError: false,
      setPasswordResendCooldown: 0,
    }));
    clearPasswordCooldownTimer();
  }

  function getTelegramOAuthClientId() {
    const value =
      typeof telegramOAuthClientId === "function" ? telegramOAuthClientId() : telegramOAuthClientId;
    return Number(value || 0);
  }

  function currentUserRecord() {
    return asRecord(getCurrentUser());
  }

  function currentTelegramLinkPendingUserId() {
    const currentUser = currentUserRecord();
    const id = currentUser.user_id ?? currentUser.id;
    return id == null ? "" : String(id);
  }

  function isTelegramLinkPendingAction(action: unknown): action is TelegramLinkPendingAction {
    return [TELEGRAM_LINK_ACTION_TRIAL, TELEGRAM_LINK_ACTION_REFERRAL_WELCOME].includes(
      String(action)
    );
  }

  function rememberTelegramLinkPendingAction(action: TelegramLinkPendingAction) {
    if (typeof window === "undefined" || !isTelegramLinkPendingAction(action)) return;
    try {
      window.sessionStorage.setItem(
        TELEGRAM_LINK_PENDING_ACTION_STORAGE_KEY,
        JSON.stringify({
          action,
          userId: currentTelegramLinkPendingUserId(),
          createdAt: Date.now(),
        })
      );
    } catch (_error) {
      void _error;
    }
  }

  function clearTelegramLinkPendingAction() {
    if (typeof window === "undefined") return;
    try {
      window.sessionStorage.removeItem(TELEGRAM_LINK_PENDING_ACTION_STORAGE_KEY);
    } catch (_error) {
      void _error;
    }
  }

  function readTelegramLinkPendingAction(): TelegramLinkPendingAction | null {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.sessionStorage.getItem(TELEGRAM_LINK_PENDING_ACTION_STORAGE_KEY);
      if (!raw) return null;
      const payload = JSON.parse(raw);
      const action = String(payload?.action || "");
      const createdAt = Number(payload?.createdAt || 0);
      const pendingUserId = String(payload?.userId || "");
      const currentUserId = currentTelegramLinkPendingUserId();
      if (
        !isTelegramLinkPendingAction(action) ||
        !createdAt ||
        Date.now() - createdAt > TELEGRAM_LINK_PENDING_TTL_MS ||
        (pendingUserId && currentUserId && pendingUserId !== currentUserId)
      ) {
        clearTelegramLinkPendingAction();
        return null;
      }
      return action;
    } catch (_error) {
      clearTelegramLinkPendingAction();
      return null;
    }
  }

  async function runTelegramLinkedAction(action: TelegramLinkPendingAction) {
    if (action === TELEGRAM_LINK_ACTION_TRIAL) {
      await activateTrial();
      return true;
    }
    if (action === TELEGRAM_LINK_ACTION_REFERRAL_WELCOME) {
      await claimReferralWelcomeBonus();
      return true;
    }
    return false;
  }

  function closeSetPasswordDialog() {
    updateState((s) => ({
      ...s,
      setPasswordOpen: false,
      setPasswordBusy: false,
      setPasswordPending: false,
      setPasswordValue: "",
      setPasswordConfirm: "",
      setPasswordCode: "",
      setPasswordStatus: "",
      setPasswordIsError: false,
      setPasswordResendCooldown: 0,
    }));
    clearPasswordCooldownTimer();
  }

  function validatePasswordDraft() {
    const s = state;
    const password = String(s.setPasswordValue || "");
    const passwordConfirm = String(s.setPasswordConfirm || "");
    if (password.length < 8) {
      setPasswordStatus(t("wa_password_too_short"), true);
      return false;
    }
    if (password.length > 128) {
      setPasswordStatus(t("wa_password_too_long"), true);
      return false;
    }
    if (password !== passwordConfirm) {
      setPasswordStatus(t("wa_password_mismatch"), true);
      return false;
    }
    return true;
  }

  async function requestLinkEmailCode() {
    const s = state;
    const normalized = String(s.linkEmailValue || "")
      .trim()
      .toLowerCase();
    if (
      s.linkEmailPending &&
      s.linkEmailResendCooldown > 0 &&
      (!normalized || normalized === s.linkEmailPending)
    ) {
      updateState((s) => ({ ...s, linkEmailOpen: true }));
      return;
    }
    if (!normalized || !normalized.includes("@")) {
      updateState((s) => ({ ...s, linkEmailFieldError: t("wa_auth_invalid_email") }));
      return;
    }
    updateState((s) => ({ ...s, linkEmailFieldError: "", linkEmailBusy: true }));
    setLinkEmailStatus(t("wa_auth_sending_code"));
    try {
      const payload: PostPayload<"/api/account/email/request"> = { email: normalized };
      const response = await api("/account/email/request", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      const responsePayload = unwrap(response);
      const presetCode = String(responsePayload.email_code || responsePayload.code || "")
        .replace(/\D/g, "")
        .slice(0, 6);
      updateState((s) => ({ ...s, linkEmailPending: normalized, linkEmailCode: presetCode }));
      setLinkEmailStatus("");
      startCooldownTimer(60);
    } catch (error: unknown) {
      setLinkEmailStatus(emailError(error, t("wa_auth_send_code_failed"), t), true);
    } finally {
      updateState((s) => ({ ...s, linkEmailBusy: false }));
    }
  }

  async function verifyLinkEmailCode() {
    const s = state;
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
    updateState((s) => ({ ...s, linkEmailBusy: true }));
    setLinkEmailStatus(t("wa_auth_checking_code"));
    try {
      const payload: PostPayload<"/api/account/email/verify"> = {
        email: s.linkEmailPending,
        code,
      };
      const response = await api("/account/email/verify", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      const csrfToken = stringField(unwrap(response).csrf_token);
      if (csrfToken) setToken("", csrfToken);
      await loadData();
      closeLinkEmailDialog();
      showToast(t("wa_settings_linked"));
    } catch (error: unknown) {
      setLinkEmailStatus(emailError(error, t("wa_auth_invalid_code"), t), true);
    } finally {
      updateState((s) => ({ ...s, linkEmailBusy: false }));
    }
  }

  async function requestSetPasswordCode() {
    const s = state;
    if (s.setPasswordPending && s.setPasswordResendCooldown > 0) {
      updateState((s) => ({ ...s, setPasswordOpen: true }));
      return;
    }
    if (!validatePasswordDraft()) return;
    updateState((s) => ({ ...s, setPasswordBusy: true }));
    setPasswordStatus(t("wa_auth_sending_code"));
    try {
      const response = await api("/account/password/request", {
        method: "POST",
        body: JSON.stringify({} as PostPayload<"/api/account/password/request">),
      });
      if (!response?.ok) throw response;
      updateState((s) => ({ ...s, setPasswordPending: true, setPasswordCode: "" }));
      setPasswordStatus("");
      startPasswordCooldownTimer(60);
    } catch (error: unknown) {
      setPasswordStatus(emailError(error, t("wa_password_code_send_failed"), t), true);
    } finally {
      updateState((s) => ({ ...s, setPasswordBusy: false }));
    }
  }

  async function confirmSetPassword() {
    const s = state;
    if (!validatePasswordDraft()) return;
    const code = String(s.setPasswordCode || "")
      .replace(/\D/g, "")
      .slice(0, 6);
    if (code.length !== 6) {
      setPasswordStatus(t("wa_auth_enter_code_6digits"), true);
      return;
    }
    updateState((s) => ({ ...s, setPasswordBusy: true }));
    setPasswordStatus(t("wa_auth_checking_code"));
    try {
      const payload: PostPayload<"/api/account/password/confirm"> = {
        password: s.setPasswordValue,
        password_confirm: s.setPasswordConfirm,
        code,
      };
      const response = await api("/account/password/confirm", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      await loadData();
      closeSetPasswordDialog();
      showToast(t("wa_password_set_success"));
    } catch (error: unknown) {
      const errorCode = stringField(asRecord(error).error);
      const fallback =
        errorCode === "password_mismatch"
          ? t("wa_password_mismatch")
          : errorCode === "password_too_short"
            ? t("wa_password_too_short")
            : t("wa_password_set_failed");
      setPasswordStatus(emailError(error, fallback, t), true);
    } finally {
      updateState((s) => ({ ...s, setPasswordBusy: false }));
    }
  }

  async function linkTelegramAccountWithPayload(
    payload: PostPayload<"/api/account/telegram/link">
  ) {
    updateState((s) => ({ ...s, linkTelegramBusy: true }));
    try {
      const response = await api("/account/telegram/link", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      const csrfToken = stringField(unwrap(response).csrf_token);
      if (csrfToken) setToken("", csrfToken);
      await loadData();
      showToast(t("wa_settings_linked"));
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_auth_telegram_not_confirmed"));
    } finally {
      updateState((s) => ({ ...s, linkTelegramBusy: false }));
    }
  }

  async function linkTelegramAccount(getTelegramMiniAppInitData: () => string = () => "") {
    const s = state;
    if (s.linkTelegramBusy) return;
    const readTelegramMiniAppInitData =
      typeof getTelegramMiniAppInitData === "function" ? getTelegramMiniAppInitData : () => "";
    const isTelegramMiniAppAttempt = telegramSdk.hasLaunchParams();
    if (isTelegramMiniAppAttempt) {
      await telegramSdk.ensureForAction();
    }
    const initData = readTelegramMiniAppInitData();
    if (initData) {
      await linkTelegramAccountWithPayload({
        init_data: initData,
      } as PostPayload<"/api/account/telegram/link">);
      return;
    }
    if (!getTelegramOAuthClientId()) {
      showToast(t("wa_auth_telegram_not_configured"));
      return;
    }
    updateState((s) => ({ ...s, linkTelegramBusy: true }));
    window.location.assign(buildTelegramOAuthUrl("link", getTg()));
  }

  async function linkTelegramFromSettings() {
    if (!isDemoAuthLogin()) {
      await linkTelegramAccount(getTelegramMiniAppInitData);
      return;
    }
    updateState((s) => ({ ...s, linkTelegramBusy: true }));
    try {
      const payload: PostPayload<"/api/account/telegram/link"> = {
        auth_data: getDemoTelegramAuthPayload(),
      } as PostPayload<"/api/account/telegram/link">;
      const response = await api("/account/telegram/link", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      const csrfToken = stringField(unwrap(response).csrf_token);
      if (csrfToken) setToken("", csrfToken);
      await loadData({ fresh: true, preserveView: true });
      showToast(t("wa_settings_linked"));
    } catch (error: unknown) {
      showToast(stringField(asRecord(error).message) || t("wa_auth_telegram_not_confirmed"));
    } finally {
      updateState((s) => ({ ...s, linkTelegramBusy: false }));
    }
  }

  async function continueTelegramLinkPendingAction() {
    if (telegramLinkPendingActionBusy) return false;
    const currentUser = currentUserRecord();
    if (!currentUser.telegram_linked) return false;
    const action = readTelegramLinkPendingAction();
    if (!action) return false;
    telegramLinkPendingActionBusy = true;
    clearTelegramLinkPendingAction();
    try {
      return await runTelegramLinkedAction(action);
    } finally {
      telegramLinkPendingActionBusy = false;
    }
  }

  async function linkTelegramWithPayloadForPendingAction(
    payload: PostPayload<"/api/account/telegram/link">
  ) {
    updateState((s) => ({ ...s, linkTelegramBusy: true }));
    try {
      const response = await api("/account/telegram/link", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      const csrfToken = stringField(unwrap(response).csrf_token);
      if (csrfToken) setToken("", csrfToken);
      await loadData({ fresh: true, preserveView: true });
      const handled = await continueTelegramLinkPendingAction();
      if (!handled) {
        clearTelegramLinkPendingAction();
        showToast(t("wa_settings_linked"));
      }
    } catch (error: unknown) {
      clearTelegramLinkPendingAction();
      showToast(stringField(asRecord(error).message) || t("wa_auth_telegram_not_confirmed"));
    } finally {
      updateState((s) => ({ ...s, linkTelegramBusy: false }));
    }
  }

  async function linkTelegramForPendingAction(action: TelegramLinkPendingAction) {
    const s = state;
    if (
      !isTelegramLinkPendingAction(action) ||
      s.linkTelegramBusy ||
      telegramLinkPendingActionBusy
    ) {
      return;
    }
    const currentUser = currentUserRecord();
    if (currentUser.telegram_linked) {
      await runTelegramLinkedAction(action);
      return;
    }

    rememberTelegramLinkPendingAction(action);
    if (isDemoAuthLogin()) {
      await linkTelegramWithPayloadForPendingAction({
        auth_data: getDemoTelegramAuthPayload(),
      } as PostPayload<"/api/account/telegram/link">);
      return;
    }

    const isTelegramMiniAppAttempt = telegramSdk.hasLaunchParams();
    if (isTelegramMiniAppAttempt) {
      await telegramSdk.ensureForAction();
    }
    const initData = getTelegramMiniAppInitData();
    if (initData) {
      await linkTelegramWithPayloadForPendingAction({
        init_data: initData,
      } as PostPayload<"/api/account/telegram/link">);
      return;
    }
    if (!getTelegramOAuthClientId()) {
      clearTelegramLinkPendingAction();
      showToast(t("wa_auth_telegram_not_configured"));
      return;
    }
    await linkTelegramAccount(getTelegramMiniAppInitData);
  }

  function linkTelegramAndActivateTrial() {
    return linkTelegramForPendingAction(TELEGRAM_LINK_ACTION_TRIAL);
  }

  function linkTelegramAndClaimReferralWelcome() {
    return linkTelegramForPendingAction(TELEGRAM_LINK_ACTION_REFERRAL_WELCOME);
  }

  async function updateAccountLanguage(nextValue: string, options: Record<string, unknown> = {}) {
    const s = state;
    const normalize = normalizeLangCode;
    const language = normalize(nextValue);
    if (!language || s.languageBusy || language === currentLang()) return;
    updateState((s) => ({ ...s, languageBusy: true }));
    try {
      const payload: PostPayload<"/api/account/language"> = { language };
      const response = await api("/account/language", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (!response?.ok) throw response;
      const responsePayload = unwrap(response);
      updateLocalData(normalize(stringField(responsePayload.language) || language));
      await loadData({ fresh: true, preserveView: true, ...options });
    } catch {
      showToast(t("wa_settings_language_update_failed"));
    } finally {
      updateState((s) => ({ ...s, languageBusy: false }));
    }
  }

  async function logout() {
    if (telegramSdk.hasLaunchParams()) return;
    markManualLogout();
    clearToken();
    try {
      await publicApi("/auth/logout", { keepalive: true } as PostPayload<"/api/auth/logout">);
    } catch (_error) {
      void _error;
    }
    showLogin();
  }

  return state;
}
