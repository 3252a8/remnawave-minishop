import type { EmojiCatalog, EmojiItem } from "$lib/telegramEmoji/types";
import {
  getTelegramEmojiDeviceStorage,
  telegramDeviceStorageCall,
} from "./telegramEmojiDeviceCache";

const KEY = "minishop_emoji_catalog_v1";
const MAX_BYTES = 128 * 1024;
const RETENTION = 30 * 24 * 60 * 60 * 1000;
type Entry = { scope: string; query: string; catalog: EmojiCatalog; touched: number };
const scopes = new WeakMap<object, () => string>();
let entries: Entry[] | null = null;
let nativeLoaded: Promise<void> | null = null;
let nativeAdapter = getTelegramEmojiDeviceStorage();
let generation = 0;
let timer: ReturnType<typeof setTimeout> | null = null;
let queue = Promise.resolve();

export function registerEmojiApiCacheScope(api: object, scope: () => string): void {
  scopes.set(api, scope);
}
export function emojiApiCacheScope(api: object): string {
  const scope = scopes.get(api)?.() ?? "";
  return /^[1-9][0-9]{0,19}$/.test(scope) ? scope : "";
}
function validItem(value: unknown): value is EmojiItem {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<EmojiItem>;
  return (
    typeof item.id === "string" &&
    /^[1-9][0-9]{0,19}$/.test(item.id) &&
    typeof item.fallback === "string" &&
    item.fallback.length <= 128 &&
    (item.set_name === null ||
      (typeof item.set_name === "string" && /^[A-Za-z0-9_]{1,64}$/.test(item.set_name))) &&
    ["static", "animated", "video"].includes(item.format ?? "") &&
    (item.thumbnail_url === null ||
      (typeof item.thumbnail_url === "string" &&
        new RegExp(`^/api/admin/telegram-emoji/media/${item.id}\\?v=[a-f0-9]{16}$`).test(
          item.thumbnail_url
        )))
  );
}
function validCatalog(value: unknown): value is EmojiCatalog {
  if (!value || typeof value !== "object") return false;
  const catalog = value as Partial<EmojiCatalog>;
  return (
    Array.isArray(catalog.items) &&
    catalog.items.length <= 60 &&
    catalog.items.every(validItem) &&
    Number.isInteger(catalog.total) &&
    (catalog.total ?? -1) >= 0 &&
    Number.isInteger(catalog.offset) &&
    (catalog.offset ?? -1) >= 0 &&
    catalog.limit === 60
  );
}
function parse(value: string | null): Entry[] {
  if (!value || value.length > MAX_BYTES) return [];
  try {
    const data: unknown = JSON.parse(value);
    if (!Array.isArray(data) || data.length > 16) return [];
    return (data as unknown[]).filter((entry): entry is Entry => {
      if (!entry || typeof entry !== "object") return false;
      const item = entry as Partial<Entry>;
      return (
        typeof item.scope === "string" &&
        /^[1-9][0-9]{0,19}$/.test(item.scope) &&
        typeof item.query === "string" &&
        item.query.length <= 2048 &&
        typeof item.touched === "number" &&
        Number.isFinite(item.touched) &&
        item.touched > Date.now() - RETENTION &&
        validCatalog(item.catalog)
      );
    });
  } catch {
    return [];
  }
}
function local(): Entry[] {
  if (entries) return entries;
  try {
    entries = parse(localStorage.getItem(KEY));
  } catch {
    entries = [];
  }
  return entries;
}
async function native(): Promise<void> {
  const storage = getTelegramEmojiDeviceStorage();
  if (storage !== nativeAdapter) {
    nativeAdapter = storage;
    nativeLoaded = null;
  }
  if (!storage) return;
  return (nativeLoaded ??= (async () => {
    const ownGeneration = generation;
    const value = await telegramDeviceStorageCall<string>((callback) =>
      storage.getItem(KEY, callback)
    );
    if (ownGeneration !== generation) return;
    for (const item of parse(value)) {
      if (
        !local().some(
          (entry) =>
            entry.scope === item.scope &&
            entry.query === item.query &&
            entry.touched >= item.touched
        )
      ) {
        entries = local().filter(
          (entry) => entry.scope !== item.scope || entry.query !== item.query
        );
        entries.push(item);
      }
    }
  })());
}
function persist(): void {
  entries = local()
    .filter((entry) => entry.touched > Date.now() - RETENTION)
    .sort((a, b) => b.touched - a.touched)
    .slice(0, 16);
  let encoded = JSON.stringify(entries);
  while (new TextEncoder().encode(encoded).length > MAX_BYTES) {
    entries.pop();
    encoded = JSON.stringify(entries);
  }
  try {
    localStorage.setItem(KEY, encoded);
  } catch {
    /* Optional in restricted WebViews. */
  }
  if (timer) return;
  const ownGeneration = generation;
  timer = setTimeout(() => {
    timer = null;
    const storage = getTelegramEmojiDeviceStorage();
    if (!storage || ownGeneration !== generation) return;
    queue = queue.then(async () => {
      if (ownGeneration !== generation) return;
      await telegramDeviceStorageCall<boolean>((callback) =>
        storage.setItem(KEY, JSON.stringify(local()), callback)
      );
    });
  }, 30);
}
export async function readEmojiCatalog(scope: string, query: string): Promise<EmojiCatalog | null> {
  if (!/^[1-9][0-9]{0,19}$/.test(scope)) return null;
  const lookup = () =>
    local().find(
      (entry) =>
        entry.scope === scope && entry.query === query && entry.touched > Date.now() - RETENTION
    )?.catalog ?? null;
  const cached = lookup();
  if (cached) return cached;
  await native();
  return lookup();
}
export function emojiCatalogGeneration(): number {
  return generation;
}
export function writeEmojiCatalog(
  scope: string,
  query: string,
  catalog: EmojiCatalog,
  expectedGeneration = generation
): void {
  if (
    expectedGeneration !== generation ||
    !/^[1-9][0-9]{0,19}$/.test(scope) ||
    query.length > 2048 ||
    !validCatalog(catalog)
  )
    return;
  entries = local().filter((entry) => entry.scope !== scope || entry.query !== query);
  entries.unshift({ scope, query, catalog, touched: Date.now() });
  persist();
}
export async function catalogEmojiPreviewUrl(scope: string, id: string): Promise<string | null> {
  if (!/^[1-9][0-9]{0,19}$/.test(scope)) return null;
  if (!local().some((entry) => entry.scope === scope)) await native();
  for (const entry of local()
    .filter((item) => item.scope === scope && item.touched > Date.now() - RETENTION)
    .sort((a, b) => b.touched - a.touched)) {
    const item = entry.catalog.items.find((item) => item.id === id);
    if (item?.thumbnail_url) return item.thumbnail_url;
  }
  return null;
}
export function clearEmojiCatalogStorage(): void {
  generation += 1;
  entries = [];
  nativeLoaded = Promise.resolve();
  if (timer) clearTimeout(timer);
  timer = null;
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* Logout remains available. */
  }
  const storage = getTelegramEmojiDeviceStorage();
  if (storage)
    queue = queue.then(async () => {
      await telegramDeviceStorageCall<boolean>((callback) => storage.removeItem(KEY, callback));
    });
}
