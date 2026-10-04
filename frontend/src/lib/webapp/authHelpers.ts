import { GIFT_STORAGE_KEY, rememberReferral, readReferral } from "./session.js";
import { referralStartParam } from "./launchParams.js";

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

const AUTH_PROVIDER_ORDER = ["telegram", "email", "google", "yandex", "discord", "passkey"];

export function orderAuthProviders(providers: readonly string[]): string[] {
  const available = new Set(providers.filter(Boolean));
  return [...AUTH_PROVIDER_ORDER.filter((provider) => available.delete(provider)), ...available];
}

export function authProviderName(provider: string, t: TranslateFn): string {
  if (provider === "email") return t("wa_security_email_source");
  if (provider === "passkey") return t("wa_security_passkey_default_name");
  const names: Record<string, string> = {
    discord: "Discord",
    google: "Google",
    telegram: "Telegram",
    yandex: "Yandex",
  };
  return names[provider] || provider;
}

export function accountMergeErrorMessage(errorCode: string, t: TranslateFn): string {
  const keys: Record<string, string> = {
    provider_conflict: "wa_account_merge_provider_conflict",
    account_merge_conflict: "wa_account_merge_conflict",
    account_merge_duplicate_promo_conflict: "wa_account_merge_duplicate_promo_conflict",
    account_merge_recurring_cancel_failed: "wa_account_merge_recurring_cancel_failed",
    account_merge_google_conflict: "wa_account_merge_google_conflict",
    account_merge_yandex_conflict: "wa_account_merge_yandex_conflict",
    account_merge_provider_conflict: "wa_account_merge_provider_conflict",
    account_merge_telegram_conflict: "wa_account_merge_telegram_conflict",
    account_merge_privileged_source: "wa_account_merge_privileged_source",
    account_merge_not_required: "wa_account_merge_not_required",
    account_merge_failed: "wa_account_merge_failed",
    account_merge_required: "wa_account_merge_required",
    account_merge_confirmation_required: "wa_account_merge_confirmation_required",
    account_merge_proof_expired: "wa_account_merge_proof_expired",
  };
  return t(keys[errorCode] || "wa_account_merge_conflict");
}

function readReferralParamFromLocation(): string {
  if (typeof window === "undefined") return "";
  const params = new URLSearchParams(window.location.search);
  const referral =
    ["ref", "start", "start_param", "startapp", "tgWebAppStartParam"]
      .map((key) => referralStartParam(params.get(key)))
      .find(Boolean) || "";
  const partner = String(params.get("partner") || "").trim();
  if (partner && referral) return "ambiguous_invite";
  return partner ? `p_${partner}` : referral;
}

export function readReferralParam(tg: unknown = null): string {
  const fromQuery = readReferralParamFromLocation();
  const fromTelegram = asTelegramWebApp(tg)?.initDataUnsafe?.start_param || "";
  const candidates = [fromTelegram, fromQuery, readReferral()];
  const value = candidates.map(referralStartParam).find(Boolean) || "";
  return value ? rememberReferral(value) : readReferral();
}

export function hasReferralParam(tg: unknown = null): boolean {
  return Boolean(readReferralParam(tg));
}

export function readRegistrationInviteParam(tg: unknown = null): string {
  const referral = readReferralParam(tg);
  if (typeof window === "undefined") return referral;
  const params = new URLSearchParams(window.location.search);
  const startParams = [
    asTelegramWebApp(tg)?.initDataUnsafe?.start_param,
    ...["start", "start_param", "startapp", "tgWebAppStartParam"].map((key) => params.get(key)),
  ];
  const incomingGift = [
    params.get("gift"),
    ...startParams.map((value) => String(value || "").match(/^gift_([A-Za-z0-9_-]{43})$/)?.[1]),
  ].find((value) => typeof value === "string" && /^[A-Za-z0-9_-]{43}$/.test(value));
  if (incomingGift) return `gift_${incomingGift}`;
  if (referral) return referral;
  let storedGift = "";
  try {
    storedGift = localStorage.getItem(GIFT_STORAGE_KEY) || "";
  } catch {
    // A gift link also works when browser storage is unavailable.
  }
  return /^[A-Za-z0-9_-]{43}$/.test(storedGift) ? `gift_${storedGift}` : "";
}

export function shouldShowInviteOnlyHint(config: InviteOnlyConfig, tg: unknown = null): boolean {
  return Boolean(config?.registrationInviteOnlyEnabled) && !readRegistrationInviteParam(tg);
}

export function readTelegramAuthStatus(): string | null {
  const params = new URLSearchParams(window.location.search);
  return (params.get("telegram_auth") || "").trim().toLowerCase() || null;
}

export function readExternalAuthStatus(): { provider: string; status: string } | null {
  const params = new URLSearchParams(window.location.search);
  const [provider = "", status = ""] = (params.get("external_auth") || "")
    .trim()
    .toLowerCase()
    .split(":", 2);
  return provider && status ? { provider, status } : null;
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
    "external_auth",
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
  const referralParam = readRegistrationInviteParam(tg);
  if (referralParam) url.searchParams.set("referral_code", referralParam);
  const tariffAccessCode = String(window.location.pathname || "")
    .match(/\/checkout\/([a-f0-9]{32})\/?$/i)?.[1]
    ?.toLowerCase();
  if (tariffAccessCode) url.searchParams.set("tariff_access", tariffAccessCode);
  return url.toString();
}

export function buildExternalOAuthStartUrl(
  provider: string,
  purpose: "login" | "link" | "merge",
  language: string,
  referral = purpose === "login" ? readRegistrationInviteParam() : "",
  tariffAccessCode = ""
): string {
  const params = new URLSearchParams({ purpose, lang: language });
  if (purpose === "merge") params.set("return_to", "/settings/security");
  if (referral) params.set("ref", referral);
  const pathAccessCode =
    typeof window === "undefined"
      ? ""
      : String(window.location.pathname || "").match(/\/checkout\/([a-f0-9]{32})\/?$/i)?.[1] || "";
  const normalizedAccessCode = String(tariffAccessCode || pathAccessCode)
    .trim()
    .toLowerCase();
  if (/^[a-f0-9]{32}$/.test(normalizedAccessCode)) {
    params.set("tariff_access", normalizedAccessCode);
  }
  return `/auth/${provider}/start?${params.toString()}`;
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
