import { isEmojiPreviewBlob, onEmojiPreviewRejected } from "$lib/telegramEmoji/media";
import { clearEmojiCatalogStorage } from "./emojiCatalogStorage";
import {
  clearDeviceEmojiPreviews,
  readDeviceEmojiPreview,
  writeDeviceEmojiPreview,
} from "./telegramEmojiDeviceCache";

const DATABASE = "minishop-emoji-previews-v1";
const MAX_BYTES = 16 * 1024 * 1024;
const MAX_ENTRIES = 512;
const RETENTION = 30 * 24 * 60 * 60 * 1000;
const DEADLINE = 500;
type Entry = { key: string; size: number; expires: number; touched: number };
let database: Promise<IDBDatabase | null> | null = null;
let generation = 0;

function validEntry(value: unknown): value is Entry {
  if (!value || typeof value !== "object") return false;
  return (
    "key" in value &&
    typeof value.key === "string" &&
    "size" in value &&
    typeof value.size === "number" &&
    Number.isFinite(value.size) &&
    value.size > 0 &&
    value.size <= MAX_BYTES &&
    "expires" in value &&
    typeof value.expires === "number" &&
    Number.isFinite(value.expires) &&
    "touched" in value &&
    typeof value.touched === "number" &&
    Number.isFinite(value.touched)
  );
}

function openDatabase(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  if (database) return database;
  database = new Promise((resolve) => {
    let settled = false;
    const finish = (db: IDBDatabase | null) => {
      if (settled) {
        db?.close();
        return;
      }
      settled = true;
      clearTimeout(timer);
      resolve(db);
    };
    const timer = setTimeout(() => finish(null), DEADLINE);
    try {
      const request = indexedDB.open(DATABASE, 1);
      request.onupgradeneeded = () => {
        request.result.createObjectStore("entries", { keyPath: "key" });
        request.result.createObjectStore("blobs");
      };
      request.onerror = () => finish(null);
      request.onblocked = () => finish(null);
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => {
          db.close();
          database = null;
        };
        finish(db);
      };
    } catch {
      finish(null);
    }
  });
  return database;
}

/** Versioned admin previews only; keys contain a verified account ID, never credentials. */
export function persistentEmojiKey(scope: string, url: string): string | null {
  return /^[1-9][0-9]{0,19}$/.test(scope) &&
    /^\/api\/admin\/telegram-emoji\/media\/[1-9][0-9]{0,19}\?v=[a-f0-9]{16}$/.test(url)
    ? JSON.stringify([scope, url])
    : null;
}

function transactionResult(transaction: IDBTransaction): Promise<boolean> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      try {
        transaction.abort();
      } catch {
        /* The transaction may already have finished. */
      }
      resolve(false);
    }, DEADLINE);
    const finish = (ok: boolean) => {
      clearTimeout(timer);
      resolve(ok);
    };
    transaction.oncomplete = () => finish(true);
    transaction.onabort = transaction.onerror = () => finish(false);
  });
}

async function remove(key: string): Promise<void> {
  const db = await openDatabase();
  if (!db) return;
  try {
    const transaction = db.transaction(["entries", "blobs"], "readwrite");
    const done = transactionResult(transaction);
    transaction.objectStore("entries").delete(key);
    transaction.objectStore("blobs").delete(key);
    await done;
  } catch {
    /* Storage is optional in restricted WebViews. */
  }
}

async function readBrowserEmojiPreview(scope: string, url: string): Promise<Blob | null> {
  const key = persistentEmojiKey(scope, url);
  if (!key) return null;
  const ownGeneration = generation;
  const db = await openDatabase();
  if (!db || ownGeneration !== generation) return null;
  try {
    const transaction = db.transaction(["entries", "blobs"], "readonly");
    const done = transactionResult(transaction);
    const metadata = transaction.objectStore("entries").get(key);
    const content = transaction.objectStore("blobs").get(key);
    if (!(await done) || ownGeneration !== generation) return null;
    const entry: unknown = metadata.result;
    const blob: unknown = content.result;
    if (
      !validEntry(entry) ||
      entry.key !== key ||
      entry.expires <= Date.now() ||
      !(blob instanceof Blob) ||
      !isEmojiPreviewBlob(blob) ||
      blob.size !== entry.size
    ) {
      if (entry || blob) await remove(key);
      return null;
    }
    onEmojiPreviewRejected(blob, () => void remove(key));
    // Touch only occasionally; ordinary reads stay concurrent and read-only.
    if (Date.now() - entry.touched > 60 * 60 * 1000) void writeEmojiPreview(scope, url, blob);
    return blob;
  } catch {
    return null;
  }
}

export async function readEmojiPreview(scope: string, url: string): Promise<Blob | null> {
  const key = persistentEmojiKey(scope, url);
  if (!key) return null;
  const ownGeneration = generation;
  const native = readDeviceEmojiPreview(key);
  const browser = await readBrowserEmojiPreview(scope, url);
  const blob = browser ?? (await native);
  if (ownGeneration !== generation) return null;
  if (blob) {
    writeDeviceEmojiPreview(key, blob);
    onEmojiPreviewRejected(blob, () => void remove(key));
  }
  return blob;
}

export async function writeEmojiPreview(scope: string, url: string, blob: Blob): Promise<void> {
  const key = persistentEmojiKey(scope, url);
  if (!key || !isEmojiPreviewBlob(blob)) return;
  writeDeviceEmojiPreview(key, blob);
  const ownGeneration = generation;
  const db = await openDatabase();
  if (!db || ownGeneration !== generation) return;
  try {
    const transaction = db.transaction(["entries", "blobs"], "readwrite");
    const done = transactionResult(transaction);
    const entries = transaction.objectStore("entries");
    const blobs = transaction.objectStore("blobs");
    const request = entries.getAll();
    request.onsuccess = () => {
      if (ownGeneration !== generation || !isEmojiPreviewBlob(blob)) {
        transaction.abort();
        return;
      }
      const now = Date.now();
      const previous = (request.result as unknown[]).filter(validEntry);
      const alive = previous
        .filter((entry) => entry.key !== key && entry.expires > now)
        .sort((a, b) => a.touched - b.touched);
      let bytes = alive.reduce((sum, entry) => sum + entry.size, 0) + blob.size;
      while (alive.length >= MAX_ENTRIES || bytes > MAX_BYTES) {
        const oldest = alive.shift();
        if (!oldest) break;
        bytes -= oldest.size;
      }
      const keep = new Set(alive.map((entry) => entry.key));
      for (const entry of previous)
        if (entry.key !== key && !keep.has(entry.key)) {
          entries.delete(entry.key);
          blobs.delete(entry.key);
        }
      entries.put({ key, size: blob.size, touched: now, expires: now + RETENTION } satisfies Entry);
      blobs.put(blob, key);
    };
    if (await done) onEmojiPreviewRejected(blob, () => void remove(key));
  } catch {
    /* Quotas, private browsing and disabled storage keep the network fallback. */
  }
}

export async function clearEmojiPreviewStorage(): Promise<void> {
  generation += 1;
  clearEmojiCatalogStorage();
  clearDeviceEmojiPreviews();
  const db = await openDatabase();
  if (!db) return;
  try {
    const transaction = db.transaction(["entries", "blobs"], "readwrite");
    const done = transactionResult(transaction);
    transaction.objectStore("entries").clear();
    transaction.objectStore("blobs").clear();
    await done;
  } catch {
    /* Logout must succeed even if browser storage is unavailable. */
  }
}
