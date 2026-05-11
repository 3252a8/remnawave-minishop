import { rememberReferral, readReferral } from "./session.js";

export function readReferralParam(tg) {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("ref") || params.get("start") || params.get("start_param") || "";
  const fromTelegram = tg?.initDataUnsafe?.start_param || "";
  const value = String(fromTelegram || fromQuery || "").trim();
  return value ? rememberReferral(value) : readReferral();
}

export function readTelegramAuthStatus() {
  const params = new URLSearchParams(window.location.search);
  return (params.get("telegram_auth") || "").trim().toLowerCase() || null;
}

export function readMagicLoginToken() {
  const params = new URLSearchParams(window.location.search);
  return (params.get("login_token") || "").trim() || null;
}

export function readTelegramLoginWidgetAuthData() {
  const params = new URLSearchParams(window.location.search);
  const keys = ["id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash"];
  const authData = {};
  let hasAuthValue = false;
  keys.forEach((key) => {
    if (!params.has(key)) return;
    authData[key] = params.get(key) || "";
    hasAuthValue = true;
  });
  if (!hasAuthValue || !authData.id || !authData.auth_date || !authData.hash) return null;
  return authData;
}

export function clearAuthQuery() {
  const url = new URL(window.location.href);
  [
    "login_token",
    "login_purpose",
    "telegram_auth",
    "id",
    "first_name",
    "last_name",
    "username",
    "photo_url",
    "auth_date",
    "hash",
  ].forEach((key) => url.searchParams.delete(key));
  window.history?.replaceState?.({}, document.title, url.pathname + url.search + url.hash);
}

export function buildTelegramOAuthStartUrl(purpose = "login", tg = null) {
  const url = new URL("/auth/telegram/start", window.location.origin);
  url.searchParams.set("purpose", purpose);
  const referralParam = readReferralParam(tg);
  if (referralParam) url.searchParams.set("referral_code", referralParam);
  return url.toString();
}

export function emailError(error, fallback, t) {
  if (error?.error === "rate_limited")
    return t("wa_auth_resend_wait", { seconds: error.retry_after || 60 });
  if (error?.error === "invalid_email") return t("wa_auth_invalid_email");
  if (error?.error === "expired_code") return t("wa_auth_code_expired");
  if (error?.error === "invalid_code" || error?.error === "too_many_attempts")
    return t("wa_auth_invalid_code");
  return fallback;
}

export function createCooldownTimer() {
  let timer = null;
  let cooldown = 0;
  const listeners = new Set();
  function notify() {
    for (const fn of listeners) fn(cooldown);
  }
  function clear() {
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }
  function start(seconds = 60) {
    clear();
    cooldown = Math.max(0, Number(seconds || 60));
    notify();
    timer = window.setInterval(() => {
      if (cooldown <= 1) {
        cooldown = 0;
        clear();
        notify();
        return;
      }
      cooldown -= 1;
      notify();
    }, 1000);
  }
  function subscribe(listener) {
    listeners.add(listener);
    listener(cooldown);
    return () => listeners.delete(listener);
  }
  return {
    start,
    clear,
    subscribe,
    get value() {
      return cooldown;
    },
  };
}
