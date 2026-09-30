import { referralStartParam } from "./launchParams.js";

export const TOKEN_STORAGE_KEY = "rw_webapp_token";
export const CSRF_COOKIE_NAME = "rw_webapp_csrf";
export const REFERRAL_STORAGE_KEY = "rw_webapp_referral";

function ignoreStorageError(error: unknown): void {
  void error;
}

export function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

export function clearStoredToken(storageKey = TOKEN_STORAGE_KEY): void {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(storageKey);
}

export function markManualLogout(flagKey: string): void {
  try {
    localStorage.setItem(flagKey, "1");
  } catch (error) {
    ignoreStorageError(error);
  }
}

export function clearManualLogoutFlag(flagKey: string): void {
  try {
    localStorage.removeItem(flagKey);
  } catch (error) {
    ignoreStorageError(error);
  }
}

export function isManuallyLoggedOut(flagKey: string): boolean {
  try {
    return localStorage.getItem(flagKey) === "1";
  } catch {
    return false;
  }
}

export function rememberReferral(value: unknown): string {
  const normalized = referralStartParam(value);
  if (!normalized) return readReferral();
  try {
    localStorage.setItem(REFERRAL_STORAGE_KEY, normalized);
  } catch (error) {
    ignoreStorageError(error);
  }
  return normalized;
}

export function readReferral(): string {
  try {
    const stored = localStorage.getItem(REFERRAL_STORAGE_KEY) || "";
    const referral = referralStartParam(stored);
    if (stored && !referral) localStorage.removeItem(REFERRAL_STORAGE_KEY);
    return referral;
  } catch {
    return "";
  }
}
