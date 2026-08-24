import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { THEME_PREFERENCE_STORAGE_KEY } from "./themePreference.js";
import {
  loadThemePreference,
  readLocalThemePreference,
  saveThemePreference,
} from "./themePreferenceStorage.js";

// Tests run in the node environment (vitest.config.mjs), so window and
// localStorage come from minimal stubs — the same approach the neighbouring
// DOM-effect tests take.
function fakeLocalStorage() {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => void store.set(key, String(value)),
    removeItem: (key: string) => void store.delete(key),
    clear: () => store.clear(),
  };
}

let localStorageStub: ReturnType<typeof fakeLocalStorage>;

beforeEach(() => {
  localStorageStub = fakeLocalStorage();
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { localStorage: localStorageStub },
  });
});

function cloudStorage(stored: Record<string, string>, options: { silent?: boolean } = {}) {
  return {
    getItem: vi.fn((key: string, callback: (error: unknown, value?: unknown) => void) => {
      if (options.silent) return;
      callback(null, stored[key]);
    }),
    setItem: vi.fn((key: string, value: string) => {
      stored[key] = value;
    }),
  };
}

afterEach(() => {
  Reflect.deleteProperty(globalThis, "window");
  vi.useRealTimers();
});

describe("readLocalThemePreference", () => {
  it("returns an empty string when nothing was picked", () => {
    expect(readLocalThemePreference()).toBe("");
  });

  it("normalizes the stored mode", () => {
    localStorageStub.setItem(THEME_PREFERENCE_STORAGE_KEY, " LIGHT ");
    expect(readLocalThemePreference()).toBe("light");
  });
});

describe("saveThemePreference", () => {
  it("writes only to localStorage outside Telegram", () => {
    saveThemePreference(null, "light");
    expect(localStorageStub.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe("light");
  });

  it("writes to both CloudStorage and localStorage inside Telegram", () => {
    const stored: Record<string, string> = {};
    const storage = cloudStorage(stored);
    saveThemePreference({ CloudStorage: storage, isVersionAtLeast: () => true }, "dark");
    expect(stored[THEME_PREFERENCE_STORAGE_KEY]).toBe("dark");
    expect(localStorageStub.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe("dark");
  });

  it("leaves CloudStorage alone on an older client", () => {
    const storage = cloudStorage({});
    saveThemePreference({ CloudStorage: storage, isVersionAtLeast: () => false }, "light");
    expect(storage.setItem).not.toHaveBeenCalled();
    expect(localStorageStub.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe("light");
  });
});

describe("loadThemePreference", () => {
  it("prefers the cloud value and refreshes the local copy", async () => {
    localStorageStub.setItem(THEME_PREFERENCE_STORAGE_KEY, "light");
    const storage = cloudStorage({ [THEME_PREFERENCE_STORAGE_KEY]: "dark" });
    await expect(
      loadThemePreference({ CloudStorage: storage, isVersionAtLeast: () => true })
    ).resolves.toBe("dark");
    expect(localStorageStub.getItem(THEME_PREFERENCE_STORAGE_KEY)).toBe("dark");
  });

  it("falls back to the local copy when the cloud is empty", async () => {
    localStorageStub.setItem(THEME_PREFERENCE_STORAGE_KEY, "light");
    const storage = cloudStorage({});
    await expect(
      loadThemePreference({ CloudStorage: storage, isVersionAtLeast: () => true })
    ).resolves.toBe("light");
  });

  it("does not hang when the client never calls back", async () => {
    vi.useFakeTimers();
    localStorageStub.setItem(THEME_PREFERENCE_STORAGE_KEY, "light");
    const storage = cloudStorage({}, { silent: true });
    const pending = loadThemePreference({ CloudStorage: storage, isVersionAtLeast: () => true });
    await vi.advanceTimersByTimeAsync(1600);
    await expect(pending).resolves.toBe("light");
  });
});
