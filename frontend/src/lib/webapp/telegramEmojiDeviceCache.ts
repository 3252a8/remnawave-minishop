import { isEmojiPreviewBlob, onEmojiPreviewRejected } from "$lib/telegramEmoji/media";

type Result<T> = (error: string | null, value?: T | null) => void;
export type TelegramDeviceStorage = {
  getItem(key: string, callback: Result<string>): unknown;
  setItem(key: string, value: string, callback: Result<boolean>): unknown;
  removeItem(key: string, callback: Result<boolean>): unknown;
};

const KEY = "minishop_emoji_previews_v1";
const MAX_BYTES = 1024 * 1024;
const MAX_ENTRIES = 256;
const RETENTION = 30 * 24 * 60 * 60 * 1000;
type Entry = { key: string; mime: string; data: string; expires: number; touched: number };

export function telegramDeviceStorageCall<T>(
  operation: (callback: Result<T>) => unknown
): Promise<T | null> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), 250);
    try {
      operation((error, value) => {
        clearTimeout(timer);
        resolve(error ? null : (value ?? null));
      });
    } catch {
      clearTimeout(timer);
      resolve(null);
    }
  });
}

/** A bounded mirror in Telegram's native storage survives replacement of a WebView. */
export class TelegramEmojiDeviceCache {
  private entries = new Map<string, Entry>();
  private loaded: Promise<void> | null = null;
  private queue = Promise.resolve();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private generation = 0;

  constructor(private storage: TelegramDeviceStorage) {}

  private load(): Promise<void> {
    return (this.loaded ??= (async () => {
      const generation = this.generation;
      const value = await telegramDeviceStorageCall<string>((callback) =>
        this.storage.getItem(KEY, callback)
      );
      if (!value || value.length > MAX_BYTES || generation !== this.generation) return;
      try {
        const parsed: unknown = JSON.parse(value);
        if (!Array.isArray(parsed) || parsed.length > MAX_ENTRIES) return;
        for (const item of parsed) {
          if (
            !item ||
            typeof item !== "object" ||
            typeof item.key !== "string" ||
            typeof item.mime !== "string" ||
            !/^image\/(png|webp|jpeg|gif)$/.test(item.mime) ||
            typeof item.data !== "string" ||
            item.data.length > 180000 ||
            !Number.isFinite(item.expires) ||
            item.expires <= Date.now() ||
            !Number.isFinite(item.touched)
          )
            continue;
          this.entries.set(item.key, item as Entry);
        }
      } catch {
        /* Invalid native storage is disposable. */
      }
    })());
  }

  private schedule(): void {
    if (this.timer) return;
    this.timer = setTimeout(() => {
      this.timer = null;
      const generation = this.generation;
      this.queue = this.queue.then(async () => {
        if (generation !== this.generation) return;
        const alive = [...this.entries.values()]
          .filter((entry) => entry.expires > Date.now())
          .sort((a, b) => b.touched - a.touched)
          .slice(0, MAX_ENTRIES);
        let value = JSON.stringify(alive);
        while (value.length > MAX_BYTES) {
          alive.pop();
          value = JSON.stringify(alive);
        }
        this.entries = new Map(alive.map((entry) => [entry.key, entry]));
        await telegramDeviceStorageCall<boolean>((callback) =>
          this.storage.setItem(KEY, value, callback)
        );
      });
    }, 30);
  }

  async read(key: string): Promise<Blob | null> {
    const generation = this.generation;
    await this.load();
    if (generation !== this.generation) return null;
    const entry = this.entries.get(key);
    if (!entry || entry.expires <= Date.now()) return null;
    try {
      const decoded = atob(entry.data);
      const blob = new Blob([Uint8Array.from(decoded, (character) => character.charCodeAt(0))], {
        type: entry.mime,
      });
      if (!isEmojiPreviewBlob(blob)) throw new Error("Invalid preview");
      onEmojiPreviewRejected(blob, () => this.remove(key));
      if (Date.now() - entry.touched > 60 * 60 * 1000) {
        entry.touched = Date.now();
        entry.expires = Date.now() + RETENTION;
        this.schedule();
      }
      return blob;
    } catch {
      this.remove(key);
      return null;
    }
  }

  async write(key: string, blob: Blob): Promise<void> {
    if (!isEmojiPreviewBlob(blob) || blob.size > 128 * 1024) return;
    const generation = this.generation;
    await this.load();
    const previous = this.entries.get(key);
    if (previous && previous.expires > Date.now()) return;
    const bytes = new Uint8Array(await blob.arrayBuffer());
    if (generation !== this.generation || !isEmojiPreviewBlob(blob)) return;
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    const now = Date.now();
    this.entries.set(key, {
      key,
      mime: blob.type.toLowerCase(),
      data: btoa(binary),
      touched: now,
      expires: now + RETENTION,
    });
    onEmojiPreviewRejected(blob, () => this.remove(key));
    this.schedule();
  }

  private remove(key: string): void {
    this.entries.delete(key);
    this.schedule();
  }

  async clear(): Promise<void> {
    this.generation += 1;
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.entries.clear();
    this.loaded = Promise.resolve();
    this.queue = this.queue.then(async () => {
      await telegramDeviceStorageCall<boolean>((callback) =>
        this.storage.removeItem(KEY, callback)
      );
    });
    await this.queue;
  }
}

let adapter: TelegramDeviceStorage | null = null;
let cache: TelegramEmojiDeviceCache | null = null;
export const getTelegramEmojiDeviceStorage = (): TelegramDeviceStorage | null => adapter;
export function setTelegramEmojiDeviceStorage(storage: TelegramDeviceStorage | null): void {
  if (adapter === storage) return;
  adapter = storage;
  cache = storage ? new TelegramEmojiDeviceCache(storage) : null;
}
export const readDeviceEmojiPreview = (key: string): Promise<Blob | null> =>
  cache?.read(key) ?? Promise.resolve(null);
export const writeDeviceEmojiPreview = (key: string, blob: Blob): void => {
  void cache?.write(key, blob).catch(() => undefined);
};
export const clearDeviceEmojiPreviews = (): void => {
  void cache?.clear();
};
