export const TOKEN_STORAGE_KEY = "rw_webapp_token";
export const CSRF_COOKIE_NAME = "rw_webapp_csrf";
export const REFERRAL_STORAGE_KEY = "rw_webapp_referral";

function ignoreStorageError(error) {
  void error;
}

export function readCookie(name) {
  if (typeof document === "undefined") return "";
  const prefix = `${name}=`;
  const cookie = document.cookie.split("; ").find((part) => part.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

export function readStoredToken(storageKey = TOKEN_STORAGE_KEY) {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(storageKey) || "";
}

export function persistToken(token, storageKey = TOKEN_STORAGE_KEY) {
  if (!token || typeof localStorage === "undefined") return;
  localStorage.setItem(storageKey, token);
}

export function clearStoredToken(storageKey = TOKEN_STORAGE_KEY) {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(storageKey);
}

export function markManualLogout(flagKey) {
  try {
    localStorage.setItem(flagKey, "1");
  } catch (error) {
    ignoreStorageError(error);
  }
}

export function clearManualLogoutFlag(flagKey) {
  try {
    localStorage.removeItem(flagKey);
  } catch (error) {
    ignoreStorageError(error);
  }
}

export function isManuallyLoggedOut(flagKey) {
  try {
    return localStorage.getItem(flagKey) === "1";
  } catch {
    return false;
  }
}

export function rememberReferral(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return readReferral();
  try {
    localStorage.setItem(REFERRAL_STORAGE_KEY, normalized);
  } catch (error) {
    ignoreStorageError(error);
  }
  return normalized;
}

export function readReferral() {
  try {
    return localStorage.getItem(REFERRAL_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}
