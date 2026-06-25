type AdminUserLike = Record<string, unknown> & {
  avatar_url?: string | null;
  email?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  telegram_id?: number | string | null;
  telegram_photo_url?: string | null;
  user_id?: number | string;
  username?: string | null;
};
type TelegramWindow = Window & {
  Telegram?: {
    WebApp?: {
      openTelegramLink?: (url: string) => void;
    };
  };
};

function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function userDisplayName(user: AdminUserLike | null | undefined): string {
  const full = [user?.first_name, user?.last_name].filter(Boolean).join(" ").trim();
  return (
    full ||
    (user?.username ? `@${user.username}` : user?.email || `User #${String(user?.user_id || "—")}`)
  );
}

export function userSecondaryName(user: AdminUserLike | null | undefined): string {
  if (user?.username && userDisplayName(user) !== `@${user.username}`) return `@${user.username}`;
  if (user?.email && userDisplayName(user) !== user.email) return user.email;
  return `ID ${String(user?.user_id || "—")}`;
}

export function userInitials(user: AdminUserLike | null | undefined): string {
  const source = userDisplayName(user).replace(/^@/, "").trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return (source.slice(0, 2) || "U").toUpperCase();
}

export function userAvatarUrl(user: AdminUserLike | null | undefined): string {
  const cached = stringField(user?.avatar_url).trim();
  if (cached) return cached;
  const value = stringField(user?.telegram_photo_url).trim();
  return value && !value.startsWith("/api/account/avatar") ? value : "";
}

export function userTelegramProfileLink(user: AdminUserLike | null | undefined): string {
  const username = String(user?.username || "")
    .trim()
    .replace(/^@+/, "");
  if (username) return `https://t.me/${encodeURIComponent(username)}`;

  const telegramId = Number(user?.telegram_id);
  if (Number.isFinite(telegramId) && telegramId > 0) {
    return `tg://user?id=${encodeURIComponent(String(Math.trunc(telegramId)))}`;
  }

  return "";
}

export function userTelegramProfileLinkKind(user: AdminUserLike | null | undefined): string {
  return String(user?.username || "").trim()
    ? "username"
    : userTelegramProfileLink(user)
      ? "id"
      : "";
}

export function openTelegramProfileLink(link: string): boolean {
  if (!link || typeof window === "undefined") return false;

  const tg = (window as TelegramWindow).Telegram?.WebApp;
  if (/^https:\/\/(?:t|telegram)\.me\//i.test(link) && typeof tg?.openTelegramLink === "function") {
    try {
      tg.openTelegramLink(link);
      return true;
    } catch {
      // Fall through to the normal browser/deep-link handling below.
    }
  }

  if (/^https?:\/\//i.test(link)) {
    window.open(link, "_blank", "noopener,noreferrer");
    return true;
  }

  window.location.href = link;
  return true;
}

export function createGravatarCache(onResolved: () => void = () => {}) {
  const cache = new Map<string, string>();
  const pending = new Map<string, Promise<void>>();

  async function sha256Hex(value: string): Promise<string> {
    const buf = new TextEncoder().encode(value);
    const digest = await crypto.subtle.digest("SHA-256", buf);
    return Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }

  function gravatarUrl(email: unknown): string {
    const key = String(email || "")
      .trim()
      .toLowerCase();
    if (!key) return "";
    if (cache.has(key)) return cache.get(key) || "";
    if (pending.has(key)) return "";
    pending.set(
      key,
      sha256Hex(key)
        .then((h) => {
          cache.set(key, `https://gravatar.com/avatar/${h}?d=identicon&s=80`);
          onResolved();
        })
        .catch(() => {
          pending.delete(key);
        })
    );
    return "";
  }

  return { gravatarUrl };
}
