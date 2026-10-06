import { MANUAL_LOGOUT_FLAG_KEY } from "./constants.js";
import { publicApiUrl } from "./passkeys.js";
import { clearManualLogoutFlag } from "./session.js";

/** QR sign-in: the waiting browser only ever talks to the shop, never to Telegram. */
export const QR_LOGIN_FRAGMENT_KEY = "qrlogin";

const CODE_PATTERN = /^[A-Za-z0-9_-]{22}$/;
const LINK_PATTERN = /[#?&]qrlogin=([A-Za-z0-9_-]{22})(?=$|[&#])/;

export type QrLoginStatus = "pending" | "scanned" | "approved" | "denied" | "expired";

export type QrLoginStarted = {
  request_id: string;
  qr_url: string;
  expires_in: number;
  poll_interval: number;
};

export type QrLoginPoll = {
  status: QrLoginStatus;
  match_number?: number;
  expires_in?: number;
};

type ScanQrPopupCallback = (text: string) => boolean | void;

export type TelegramQrScanner = {
  showScanQrPopup: (params: { text?: string }, callback?: ScanQrPopupCallback) => void;
};

type TelegramScannerLike = {
  platform?: string;
  isVersionAtLeast?: (version: string) => boolean;
  showScanQrPopup?: TelegramQrScanner["showScanQrPopup"];
} | null;

/** Pull the one-time code out of whatever a scanner returned: the sign-in link or the bare code. */
export function parseQrLoginCode(text: string | null | undefined): string | null {
  const value = String(text || "").trim();
  if (CODE_PATTERN.test(value)) return value;
  return LINK_PATTERN.exec(value)?.[1] ?? null;
}

/** Telegram's own scanner exists only in the phone apps; elsewhere the page scans with the camera. */
export function telegramQrScanner(tg: unknown): TelegramQrScanner | null {
  const webApp = (tg && typeof tg === "object" ? tg : null) as TelegramScannerLike;
  const showScanQrPopup = webApp?.showScanQrPopup;
  if (!showScanQrPopup || !webApp?.isVersionAtLeast?.("6.4")) return null;
  if (!["android", "ios"].includes(String(webApp.platform || ""))) return null;
  return { showScanQrPopup: showScanQrPopup.bind(webApp) };
}

/** Read a sign-in code from the address once and drop it, so a reload cannot reuse it. */
export function takeQrLoginCodeFromLocation(): string | null {
  if (typeof window === "undefined") return null;
  const code = parseQrLoginCode(window.location.hash);
  if (!code) return null;
  const { pathname, search } = window.location;
  window.history.replaceState(window.history.state, "", `${pathname}${search}`);
  return code;
}

async function postPublic(url: string, body: unknown = {}): Promise<Record<string, unknown>> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "same-origin",
  });
  return (await response.json()) as Record<string, unknown>;
}

export async function startQrLogin(apiBase = "/api"): Promise<QrLoginStarted> {
  const response = await postPublic(publicApiUrl(apiBase, "/auth/qr/start"));
  if (!response.ok) throw response;
  return response as unknown as QrLoginStarted;
}

export async function pollQrLogin(apiBase: string, requestId: string): Promise<QrLoginPoll> {
  const response = await postPublic(publicApiUrl(apiBase, "/auth/qr/poll"), {
    request_id: requestId,
  });
  if (!response.ok) throw response;
  return response as unknown as QrLoginPoll;
}

export async function cancelQrLogin(apiBase = "/api"): Promise<void> {
  await postPublic(publicApiUrl(apiBase, "/auth/qr/cancel")).catch(() => undefined);
}

/** The poll that saw the approval already set the session cookies; open the app like other logins. */
export function finishQrLogin(): void {
  clearManualLogoutFlag(MANUAL_LOGOUT_FLAG_KEY);
  window.location.assign("/home");
}
