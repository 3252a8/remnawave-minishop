import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EmojiCatalog } from "$lib/telegramEmoji/types";
import { getEmojiCatalog } from "$lib/telegramEmoji/api";
import { createApiClient } from "./publicApi";
import {
  catalogEmojiPreviewUrl,
  clearEmojiCatalogStorage,
  emojiApiCacheScope,
  emojiApiCatalogCache,
  emojiCatalogGeneration,
  readEmojiCatalog,
  registerEmojiApiCacheScope,
  writeEmojiCatalog,
} from "./emojiCatalogStorage";
import {
  setTelegramEmojiDeviceStorage,
  type TelegramDeviceStorage,
} from "./telegramEmojiDeviceCache";
import { writeEmojiPreview, clearEmojiPreviewStorage } from "./emojiPreviewStorage";

const KEY = "minishop_emoji_catalog_v1";
const url = "/api/admin/telegram-emoji/media/5368651601797984900?v=0123456789abcdef";
const query = "offset=0&limit=60";
const catalog = (): EmojiCatalog => ({
  items: [
    {
      id: "5368651601797984900",
      fallback: "🖥",
      set_name: "win95_by_emjsetbot",
      thumbnail_url: url,
      format: "static",
    },
  ],
  total: 1,
  offset: 0,
  limit: 60,
});
let values: Map<string, string>;
beforeEach(() => {
  setTelegramEmojiDeviceStorage(null);
  values = new Map();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  });
  clearEmojiCatalogStorage();
});
afterEach(async () => {
  setTelegramEmojiDeviceStorage(null);
  await clearEmojiPreviewStorage();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("persistent emoji catalog", () => {
  it("shares storage and invalidation with a separately loaded admin bundle", async () => {
    writeEmojiCatalog("42", query, catalog());
    let finish!: (response: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          })
      )
    );
    const mainClient = createApiClient({
      getAuthToken: () => "session",
      getEmojiCacheScope: () => "42",
    });
    const mainCache = emojiApiCatalogCache(mainClient.api);
    vi.resetModules();
    const adminStorage = await import("./emojiCatalogStorage");
    const adminApi = await import("$lib/telegramEmoji/api");
    expect(adminStorage.emojiApiCatalogCache(mainClient.api)).toBe(mainCache);
    expect(adminStorage.emojiApiCacheScope(mainClient.api)).toBe("42");
    const refreshed = vi.fn();
    expect(await adminApi.getEmojiCatalog(mainClient.api, {}, undefined, refreshed)).toEqual(
      catalog()
    );
    expect(refreshed).not.toHaveBeenCalled();
    const fresh = catalog();
    fresh.items[0].thumbnail_url = url.replace("0123456789abcdef", "0000000000000001");
    finish(
      new Response(JSON.stringify({ ok: true, ...fresh }), {
        headers: { "Content-Type": "application/json" },
      })
    );
    await vi.waitFor(() => expect(refreshed).toHaveBeenCalledWith({ ok: true, ...fresh }));
    expect(await catalogEmojiPreviewUrl("42", fresh.items[0].id)).toBe(
      fresh.items[0].thumbnail_url
    );
    vi.mocked(fetch).mockImplementation(
      async () =>
        new Response(
          JSON.stringify({
            ok: true,
            library: { schema_version: 1, sets: [], manual_ids: [] },
            revision: "a".repeat(64),
            sets: [],
          }),
          { headers: { "Content-Type": "application/json" } }
        )
    );
    await adminApi.removeEmojiSource(mainClient.api, "win95_by_emjsetbot", "a".repeat(64));
    expect(await readEmojiCatalog("42", query)).toBeNull();
    expect(await catalogEmojiPreviewUrl("42", catalog().items[0].id)).toBeNull();
  });
  it("renders stored metadata without waiting for background HTTP and applies refreshed versions", async () => {
    writeEmojiCatalog("42", query, catalog());
    let finish!: (value: unknown) => void;
    const api = vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        })
    ) as unknown as ReturnType<typeof createApiClient>["api"];
    registerEmojiApiCacheScope(api, () => "42");
    const refreshed = vi.fn();
    expect(await getEmojiCatalog(api, {}, undefined, refreshed)).toEqual(catalog());
    expect(refreshed).not.toHaveBeenCalled();
    const fresh = catalog();
    fresh.items[0].thumbnail_url = url.replace("0123456789abcdef", "0000000000000001");
    finish({ ok: true, ...fresh });
    await vi.waitFor(() => expect(refreshed).toHaveBeenCalledWith({ ok: true, ...fresh }));
    expect(await catalogEmojiPreviewUrl("42", fresh.items[0].id)).toBe(
      fresh.items[0].thumbnail_url
    );
  });
  it("uses verified account scope across token changes and excludes anonymous clients", async () => {
    writeEmojiCatalog("42", query, catalog());
    const first = createApiClient({
      getAuthToken: () => "token-a",
      getEmojiCacheScope: () => "42",
    });
    const reopened = createApiClient({
      getAuthToken: () => "token-b",
      getEmojiCacheScope: () => "42",
    });
    expect(emojiApiCacheScope(first.api)).toBe(emojiApiCacheScope(reopened.api));
    expect(emojiApiCacheScope(createApiClient({ getEmojiCacheScope: () => "42" }).api)).toBe("");
    expect(await readEmojiCatalog("43", query)).toBeNull();
    expect(await catalogEmojiPreviewUrl("43", catalog().items[0].id)).toBeNull();
    expect(values.get(KEY)).not.toContain("token-");
  });
  it("does not resurrect metadata from requests started before logout or library invalidation", async () => {
    let finish!: (value: unknown) => void;
    const api = vi.fn(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        })
    ) as unknown as ReturnType<typeof createApiClient>["api"];
    registerEmojiApiCacheScope(api, () => "42");
    const pending = getEmojiCatalog(api);
    clearEmojiCatalogStorage();
    finish({ ok: true, ...catalog() });
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
    expect(await readEmojiCatalog("42", query)).toBeNull();
    const oldGeneration = emojiCatalogGeneration();
    clearEmojiCatalogStorage();
    writeEmojiCatalog("42", query, catalog(), oldGeneration);
    expect(values.has(KEY)).toBe(false);
  });
  it("bounds pages and bytes and rejects corrupt or external preview URLs", async () => {
    for (let index = 0; index < 30; index++) writeEmojiCatalog("42", String(index), catalog());
    expect((JSON.parse(values.get(KEY)!) as unknown[]).length).toBe(16);
    const large = catalog();
    large.total = 60;
    large.items = Array.from({ length: 60 }, () => ({
      ...catalog().items[0],
      fallback: "🖥".repeat(60),
    }));
    for (let index = 0; index < 30; index++) writeEmojiCatalog("42", `large${index}`, large);
    expect(new TextEncoder().encode(values.get(KEY)!).length).toBeLessThanOrEqual(128 * 1024);
    const invalid = catalog();
    invalid.items[0].thumbnail_url = "https://third-party.invalid/track";
    writeEmojiCatalog("42", "invalid", invalid);
    expect(await readEmojiCatalog("42", "invalid")).toBeNull();
    vi.useFakeTimers();
    vi.setSystemTime(Date.now() + 31 * 86400000);
    expect(await readEmojiCatalog("42", "29")).toBeNull();
  });
  it("restores metadata from Telegram native storage when a new WebView has no local storage", async () => {
    vi.useFakeTimers();
    const nativeValues = new Map<string, string>([["unrelated", "keep"]]);
    const storage: TelegramDeviceStorage = {
      getItem: vi.fn((key, callback) => callback(null, nativeValues.get(key) ?? null)),
      setItem: vi.fn((key, value, callback) => {
        nativeValues.set(key, value);
        callback(null, true);
      }),
      removeItem: vi.fn((key, callback) => {
        nativeValues.delete(key);
        callback(null, true);
      }),
    };
    setTelegramEmojiDeviceStorage(storage);
    writeEmojiCatalog("42", query, catalog());
    await vi.advanceTimersByTimeAsync(40);
    expect(storage.setItem).toHaveBeenCalledTimes(1);
    // Simulate a fresh JavaScript module and unavailable browser storage.
    vi.resetModules();
    vi.stubGlobal("localStorage", undefined);
    const native = await import("./telegramEmojiDeviceCache");
    native.setTelegramEmojiDeviceStorage(storage);
    const reopened = await import("./emojiCatalogStorage");
    expect(await reopened.readEmojiCatalog("42", query)).toEqual(catalog());
    expect(await reopened.readEmojiCatalog("42", query)).toEqual(catalog());
    expect(storage.getItem).toHaveBeenCalledTimes(1);
    reopened.clearEmojiCatalogStorage();
    await vi.advanceTimersByTimeAsync(40);
    expect([...nativeValues.entries()]).toEqual([["unrelated", "keep"]]);
    native.setTelegramEmojiDeviceStorage(null);
  });
  it("reuses persisted pixels for unversioned admin previews across API instances", async () => {
    vi.stubGlobal("indexedDB", undefined);
    const nativeValues = new Map<string, string>();
    const storage: TelegramDeviceStorage = {
      getItem: (key, callback) => callback(null, nativeValues.get(key) ?? null),
      setItem: (key, value, callback) => {
        nativeValues.set(key, value);
        callback(null, true);
      },
      removeItem: (key, callback) => {
        nativeValues.delete(key);
        callback(null, true);
      },
    };
    setTelegramEmojiDeviceStorage(storage);
    writeEmojiCatalog("42", query, catalog());
    await writeEmojiPreview("42", url, new Blob(["own preview"], { type: "image/png" }));
    const fetchMock = vi.fn(
      async () => new Response("ticket preview", { headers: { "Content-Type": "image/png" } })
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({
      getAuthToken: () => "new-token",
      getEmojiCacheScope: () => "42",
    });
    expect(await (await client.apiBlob(url.split("?")[0])).text()).toBe("own preview");
    expect(fetchMock).not.toHaveBeenCalled();
    await client.apiBlob("/api/support/tickets/7/emoji/5368651601797984900");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
