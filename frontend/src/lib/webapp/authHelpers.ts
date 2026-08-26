import { rememberReferral, readReferral } from "./session.js";
import { isCheckoutStartParam } from "./deeplinks.js";

type TelegramWebAppLike = {
  initDataUnsafe?: { start_param?: string | null } | null;
} | null;

type InviteOnlyConfig = {
  registrationInviteOnlyEnabled?: unknown;
} | null;

export type TelegramLoginWidgetAuthData = Record<string, string>;

type AuthErrorLike = {
  error?: string;
  retry_after?: number;
} | null;

function asTelegramWebApp(tg: unknown): TelegramWebAppLike {
  return tg && typeof tg === "object" ? (tg as TelegramWebAppLike) : null;
}

type TranslateFn = (key: string, params?: Record<string, unknown>) => string;

function readReferralParamFromLocation(): string {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams(window.location.search);
  const referral = params.get("ref") || params.get("start") || params.get("start_param") || "";
  const partner = String(params.get("partner") || "").trim();
  if (partner && referral) return "ambiguous_invite";
  return partner ? `p_${partner}` : referral;
}

export function readReferralParam(tg: unknown = null): string {
  const fromQuery = readReferralParamFromLocation();
  const fromTelegram = asTelegramWebApp(tg)?.initDataUnsafe?.start_param || "";
  const candidates = [fromTelegram, fromQuery, readReferral()];
  const value = String(
    candidates.find((candidate) => {
      const normalized = String(candidate || "").trim();
      return normalized && !isCheckoutStartParam(normalized);
    }) || ""
  ).trim();
  return value ? rememberReferral(value) : readReferral();
}

export function hasReferralParam(tg: unknown = null): boolean {
  return Boolean(readReferralParam(tg));
}

export function shouldShowInviteOnlyHint(config: InviteOnlyConfig, tg: unknown = null): boolean {
  return Boolean(config?.registrationInviteOnlyEnabled) && !hasReferralParam(tg);
}

export function readTelegramAuthStatus(): string | null {
  const params = new URLSearchParams(window.location.search);
  return (params.get("telegram_auth") || "").trim().toLowerCase() || null;
}

export function readMagicLoginToken(): string | null {
  const params = new URLSearchParams(window.location.search);
  return (params.get("login_token") || "").trim() || null;
}

export function readTelegramLoginWidgetAuthData(): TelegramLoginWidgetAuthData | null {
  const params = new URLSearchParams(window.location.search);
  const keys = ["id", "first_name", "last_name", "username", "photo_url", "auth_date", "hash"];
  const authData: TelegramLoginWidgetAuthData = {};
  let hasAuthValue = false;
  keys.forEach((key) => {
    if (!params.has(key)) return;
    authData[key] = params.get(key) || "";
    hasAuthValue = true;
  });
  if (!hasAuthValue || !authData.id || !authData.auth_date || !authData.hash) return null;
  return authData;
}

export function clearAuthQuery(): void {
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
    "partner",
    "ref",
    "start",
    "start_param",
  ].forEach((key) => url.searchParams.delete(key));
  window.history?.replaceState?.({}, document.title, url.pathname + url.search + url.hash);
}

export function buildTelegramOAuthStartUrl(purpose = "login", tg: unknown = null): string {
  const url = new URL("/auth/telegram/start", window.location.origin);
  url.searchParams.set("purpose", purpose);
  const referralParam = readReferralParam(tg);
  if (referralParam) url.searchParams.set("referral_code", referralParam);
  return url.toString();
}

export function emailError(error: unknown, fallback: string, t: TranslateFn): string {
  const err: AuthErrorLike = error && typeof error === "object" ? (error as AuthErrorLike) : null;
  if (err?.error === "rate_limited")
    return t("wa_auth_resend_wait", { seconds: err.retry_after || 60 });
  if (err?.error === "invalid_email") return t("wa_auth_invalid_email");
  if (err?.error === "expired_code") return t("wa_auth_code_expired");
  if (err?.error === "invalid_code" || err?.error === "too_many_attempts")
    return t("wa_auth_invalid_code");
  if (err?.error === "registration_invite_required") return t("wa_auth_invite_required");
  return fallback;
}

export function createCooldownTimer() {
  let timer: number | null = null;
  let cooldown = 0;
  const listeners = new Set<(value: number) => void>();
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
  function subscribe(listener: (value: number) => void) {
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
