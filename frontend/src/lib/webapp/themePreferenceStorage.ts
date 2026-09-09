// Persistence for the user's light/dark mode choice.
//
// Inside Telegram: CloudStorage (Bot API 6.9+), so the choice belongs to the
// user and travels between their devices. In a browser and on older clients:
// localStorage. Writes always go to both — localStorage applies the theme on the
// first frame while the asynchronous CloudStorage read is still in flight.

import { normalizeThemePreference, THEME_PREFERENCE_STORAGE_KEY } from "./themePreference.js";

type CloudStorageCallback = (error: unknown, value?: unknown) => void;

type TelegramCloudStorage = {
  getItem?: (key: string, callback: CloudStorageCallback) => unknown;
  setItem?: (key: string, value: string, callback?: CloudStorageCallback) => unknown;
};

export type TelegramStorageHost = {
  CloudStorage?: TelegramCloudStorage | null;
  isVersionAtLeast?: (version: string) => boolean;
} | null;

const CLOUD_STORAGE_MIN_VERSION = "6.9";

function cloudStorageOf(tg: TelegramStorageHost): TelegramCloudStorage | null {
  if (!tg) return null;
  const storage = tg.CloudStorage;
  if (!storage || typeof storage.getItem !== "function") return null;
  // Not every SDK wrapper exposes isVersionAtLeast; without it, trust the
  // presence of the CloudStorage object itself.
  if (
    typeof tg.isVersionAtLeast === "function" &&
    !tg.isVersionAtLeast(CLOUD_STORAGE_MIN_VERSION)
  ) {
    return null;
  }
  return storage;
}

/** Synchronous read for the first frame. */
export function readLocalThemePreference(): string {
  try {
    if (typeof window === "undefined") return "";
    const raw = window.localStorage?.getItem(THEME_PREFERENCE_STORAGE_KEY);
    return raw ? normalizeThemePreference(raw) : "";
  } catch {
    // Private mode or blocked site data: there simply is no preference.
    return "";
  }
}

function writeLocalThemePreference(value: string): void {
  try {
    if (typeof window === "undefined") return;
    window.localStorage?.setItem(THEME_PREFERENCE_STORAGE_KEY, value);
  } catch {
    // Not critical: the theme still applies, it just is not remembered.
  }
}

function readCloudThemePreference(tg: TelegramStorageHost): Promise<string> {
  const storage = cloudStorageOf(tg);
  const getItem = storage?.getItem;
  if (!storage || !getItem) return Promise.resolve("");
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value: string) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    try {
      getItem.call(storage, THEME_PREFERENCE_STORAGE_KEY, (error, value) => {
        if (error) {
          finish("");
          return;
        }
        const raw = String(value || "").trim();
        finish(raw ? normalizeThemePreference(raw) : "");
      });
    } catch {
      finish("");
    }
    // The CloudStorage callback comes from the native client and may never
    // arrive (old client, rejected request); never block theme loading on it.
    setTimeout(() => finish(""), 1500);
  });
}

/**
 * The effective stored preference. The cloud value wins over the local cache
 * because the user may have switched modes on another device. An empty string
 * means the user never chose anything.
 */
export async function loadThemePreference(tg: TelegramStorageHost): Promise<string> {
  const cloud = await readCloudThemePreference(tg);
  if (cloud) {
    writeLocalThemePreference(cloud);
    return cloud;
  }
  return readLocalThemePreference();
}

export function saveThemePreference(tg: TelegramStorageHost, value: unknown): void {
  const normalized = normalizeThemePreference(value);
  writeLocalThemePreference(normalized);
  const storage = cloudStorageOf(tg);
  if (!storage?.setItem) return;
  try {
    storage.setItem(THEME_PREFERENCE_STORAGE_KEY, normalized);
  } catch {
    // The local copy is already written; the cloud is a bonus.
  }
}
