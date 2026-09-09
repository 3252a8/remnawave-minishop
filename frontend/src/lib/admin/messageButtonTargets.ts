export const CUSTOMER_WEBAPP_SECTIONS = [
  "plans",
  "home",
  "install",
  "trial",
  "invite",
  "partner",
  "devices",
  "support",
  "settings",
  "notifications",
] as const;

const TELEGRAM_HOSTS = new Set(["t.me", "telegram.me", "www.t.me", "www.telegram.me"]);
const TELEGRAM_SHORT_PREFIXES = ["t.me/", "telegram.me/", "www.t.me/", "www.telegram.me/"];
const TELEGRAM_USERNAME_RE = /^[A-Za-z0-9_]{5,32}$/;

/** Validate a button link and canonicalize Telegram shortcuts to ``https://t.me``. */
export function normalizeMessageButtonLink(value: unknown): string | null {
  let raw = String(value || "").trim();
  if (
    !raw ||
    raw.length > 2048 ||
    [...raw].some((character) => /\s/.test(character) || character.charCodeAt(0) < 32)
  )
    return null;

  if (raw.startsWith("@")) {
    const username = raw.slice(1).trim();
    if (!TELEGRAM_USERNAME_RE.test(username)) return null;
    raw = `https://t.me/${username}`;
  } else if (TELEGRAM_SHORT_PREFIXES.some((prefix) => raw.toLowerCase().startsWith(prefix))) {
    raw = `https://${raw}`;
  }

  let parsed: URL;
  try {
    parsed = new URL(raw);
  } catch {
    return null;
  }
  if (!(["http:", "https:"] as string[]).includes(parsed.protocol)) return null;
  if (!parsed.hostname || parsed.username || parsed.password) return null;

  if (TELEGRAM_HOSTS.has(parsed.hostname.toLowerCase())) {
    if (!parsed.pathname.replaceAll("/", "")) return null;
    return `https://t.me${parsed.pathname}${parsed.search}${parsed.hash}`;
  }

  const scheme = parsed.protocol.slice(0, -1).toLowerCase();
  return `${scheme}://${raw.replace(/^[a-z]+:\/\//i, "")}`;
}

export function isTelegramMessageButtonLink(value: unknown): boolean {
  return normalizeMessageButtonLink(value)?.startsWith("https://t.me/") ?? false;
}
