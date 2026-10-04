import type { TelegramEmojiApi } from "./api";
import type { MenuAppearance } from "./types";

type CachedDraft = { revision: string; saved: MenuAppearance; draft: MenuAppearance };
const drafts = new WeakMap<TelegramEmojiApi, Map<string, CachedDraft>>();

export function readMenuDraft(api: TelegramEmojiApi, adminId: string): CachedDraft | undefined {
  const value = adminId ? drafts.get(api)?.get(adminId) : undefined;
  return value ? structuredClone(value) : undefined;
}

export function cacheMenuDraft(api: TelegramEmojiApi, adminId: string, value: CachedDraft): void {
  if (!adminId) return;
  let administrators = drafts.get(api);
  if (!administrators) {
    administrators = new Map();
    drafts.set(api, administrators);
  }
  administrators.set(adminId, structuredClone(value));
}

export function clearMenuDraft(api: TelegramEmojiApi, adminId: string): void {
  drafts.get(api)?.delete(adminId);
}

export function clearMenuDrafts(api: TelegramEmojiApi): void {
  drafts.delete(api);
}
