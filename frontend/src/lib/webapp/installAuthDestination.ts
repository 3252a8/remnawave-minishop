import { installTargetFromSearch, installTargetSearch } from "./installTargets.js";

const STORAGE_KEY = "remnawave:install-auth-destination";
const MAX_AGE_MS = 15 * 60 * 1000;
const installPath = /^(?:\/[A-Za-z0-9_-]+)*\/install\/?$/;
const loginPath = /^(?:\/login(?:\/password)?)?\/?$/;

/** Capture only an install destination; authentication and checkout keep their own return flows. */
export function rememberInstallAuthDestination(purpose: string, keepLoginPending = false): void {
  if (typeof window === "undefined") return;
  try {
    const pathname = window.location.pathname;
    if (purpose !== "login" || pathname.length > 256 || !installPath.test(pathname)) {
      if (purpose !== "login" || !keepLoginPending || !loginPath.test(pathname)) {
        window.sessionStorage.removeItem(STORAGE_KEY);
      }
      return;
    }
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        pathname,
        ...installTargetFromSearch(window.location.search),
        expiresAt: Date.now() + MAX_AGE_MS,
      })
    );
  } catch {
    // Sign-in remains available when the browser disables session storage.
  }
}

/** OAuth returns to the shop root; consume the destination once before resolving its screen. */
export function restoreInstallAuthDestination(authenticated = false): boolean {
  if (typeof window === "undefined") return false;
  const query = new URLSearchParams(window.location.search);
  if (!authenticated && !query.has("external_auth") && !query.has("telegram_auth")) return false;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    window.sessionStorage.removeItem(STORAGE_KEY);
    if (!raw) return false;
    if (!loginPath.test(window.location.pathname) && !installPath.test(window.location.pathname))
      return false;
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return false;
    const saved = parsed as Record<string, unknown>;
    if (
      typeof saved.pathname !== "string" ||
      saved.pathname.length > 256 ||
      !installPath.test(saved.pathname) ||
      typeof saved.expiresAt !== "number" ||
      saved.expiresAt <= Date.now() ||
      saved.expiresAt > Date.now() + MAX_AGE_MS
    )
      return false;
    const url = new URL(window.location.href);
    const search = installTargetSearch(url.search, {
      platform: typeof saved.platform === "string" ? saved.platform : "",
      app: typeof saved.app === "string" ? saved.app : "",
    });
    window.history.replaceState(null, "", `${saved.pathname}${search}${url.hash}`);
    return true;
  } catch {
    return false;
  }
}
