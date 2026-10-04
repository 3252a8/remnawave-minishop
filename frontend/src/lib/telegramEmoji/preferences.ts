import type { EmojiItem } from "./types";

export type EmojiPreferences = { recent: EmojiItem[]; favorites: EmojiItem[] };
const emptyPreferences = (): EmojiPreferences => ({ recent: [], favorites: [] });

function items(value: unknown): EmojiItem[] {
  if (!Array.isArray(value)) return [];
  return value
    .flatMap((entry: unknown) => {
      if (!entry || typeof entry !== "object" || !("id" in entry) || !("fallback" in entry)) {
        return [];
      }
      if (typeof entry.id !== "string" || typeof entry.fallback !== "string") return [];
      return [
        {
          id: entry.id,
          fallback: entry.fallback,
          set_name:
            "set_name" in entry && typeof entry.set_name === "string" ? entry.set_name : null,
          thumbnail_url:
            "thumbnail_url" in entry &&
            typeof entry.thumbnail_url === "string" &&
            entry.thumbnail_url.startsWith("/api/admin/telegram-emoji/media/")
              ? entry.thumbnail_url
              : null,
          format: "static" as const,
        },
      ];
    })
    .slice(0, 60);
}

export function readEmojiPreferences(adminId: string): EmojiPreferences {
  if (!adminId || typeof localStorage === "undefined") return emptyPreferences();
  try {
    const value: unknown = JSON.parse(localStorage.getItem(`telegram-emoji:${adminId}`) || "null");
    if (!value || typeof value !== "object") return emptyPreferences();
    return {
      recent: "recent" in value ? items(value.recent) : [],
      favorites: "favorites" in value ? items(value.favorites) : [],
    };
  } catch {
    return emptyPreferences();
  }
}

export function writeEmojiPreferences(adminId: string, preferences: EmojiPreferences): void {
  if (!adminId || typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(`telegram-emoji:${adminId}`, JSON.stringify(preferences));
  } catch {
    // Private browsing or a full storage quota still permits selection for this session.
  }
}
