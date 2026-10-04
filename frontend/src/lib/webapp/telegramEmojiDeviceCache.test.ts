import { afterEach, describe, expect, it, vi } from "vitest";
import { isEmojiPreviewBlob, rejectEmojiPreviewBlob } from "$lib/telegramEmoji/media";
import {
  persistentEmojiKey,
  readEmojiPreview,
  writeEmojiPreview,
  clearEmojiPreviewStorage,
} from "./emojiPreviewStorage";
import {
  TelegramEmojiDeviceCache,
  setTelegramEmojiDeviceStorage,
  type TelegramDeviceStorage,
} from "./telegramEmojiDeviceCache";

const key = persistentEmojiKey(
  "42",
  "/api/admin/telegram-emoji/media/5368651601797984900?v=0123456789abcdef"
)!;
const blob = () => new Blob(["preview"], { type: "image/png" });
function device() {
  const values = new Map<string, string>([["unrelated", "keep"]]);
  const storage: TelegramDeviceStorage = {
    getItem: vi.fn((key, callback) => callback(null, values.get(key) ?? null)),
    setItem: vi.fn((key, value, callback) => {
      values.set(key, value);
      callback(null, true);
    }),
    removeItem: vi.fn((key, callback) => {
      values.delete(key);
      callback(null, true);
    }),
  };
  return { values, storage };
}
afterEach(() => {
  setTelegramEmojiDeviceStorage(null);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Telegram native preview persistence", () => {
  it("invalidates native previews when a separately loaded admin renderer rejects the Blob", async () => {
    vi.useFakeTimers();
    const { storage } = device();
    const cache = new TelegramEmojiDeviceCache(storage);
    await cache.write(key, blob());
    await vi.advanceTimersByTimeAsync(40);
    const restored = (await cache.read(key))!;
    vi.resetModules();
    const adminMedia = await import("$lib/telegramEmoji/media");
    adminMedia.rejectEmojiPreviewBlob(restored);
    expect(isEmojiPreviewBlob(restored)).toBe(false);
    await vi.advanceTimersByTimeAsync(40);
    expect(await new TelegramEmojiDeviceCache(storage).read(key)).toBeNull();
  });
  it("survives replacement of the WebView with one native read and a coalesced write", async () => {
    vi.useFakeTimers();
    const { storage } = device();
    const first = new TelegramEmojiDeviceCache(storage);
    await Promise.all(Array.from({ length: 96 }, (_, index) => first.write(key + index, blob())));
    await vi.advanceTimersByTimeAsync(40);
    expect(storage.getItem).toHaveBeenCalledTimes(1);
    expect(storage.setItem).toHaveBeenCalledTimes(1);
    const reopened = new TelegramEmojiDeviceCache(storage);
    expect(await (await reopened.read(key + "95"))!.text()).toBe("preview");
    expect(await reopened.read(key.replace('"42"', '"43"') + "95")).toBeNull();
    expect(
      await reopened.read(key.replace("0123456789abcdef", "0000000000000001") + "95")
    ).toBeNull();
    expect(storage.getItem).toHaveBeenCalledTimes(2);
  });
  it("restores previews when browser IndexedDB is unavailable", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("indexedDB", undefined);
    const { storage } = device();
    setTelegramEmojiDeviceStorage(storage);
    const url = JSON.parse(key)[1] as string;
    await writeEmojiPreview("42", url, blob());
    await vi.advanceTimersByTimeAsync(40);
    setTelegramEmojiDeviceStorage(null);
    setTelegramEmojiDeviceStorage(storage);
    expect(await (await readEmojiPreview("42", url))!.text()).toBe("preview");
    await clearEmojiPreviewStorage();
    expect(await readEmojiPreview("42", url)).toBeNull();
  });
  it("clears only its own key and prevents pending writes from repopulating it", async () => {
    vi.useFakeTimers();
    const { storage, values } = device();
    const cache = new TelegramEmojiDeviceCache(storage);
    const pending = cache.write(key, blob());
    await cache.clear();
    await pending;
    await vi.advanceTimersByTimeAsync(100);
    expect([...values.entries()]).toEqual([["unrelated", "keep"]]);
    expect(await cache.read(key)).toBeNull();
  });
  it("bounds the encoded bundle and rejects expired or corrupt previews", async () => {
    vi.useFakeTimers();
    const { storage, values } = device();
    const cache = new TelegramEmojiDeviceCache(storage);
    await Promise.all(
      Array.from({ length: 40 }, (_, index) =>
        cache.write(key + index, new Blob([new Uint8Array(32768)], { type: "image/png" }))
      )
    );
    await vi.advanceTimersByTimeAsync(40);
    const encoded = values.get("minishop_emoji_previews_v1")!;
    expect(encoded.length).toBeLessThanOrEqual(1024 * 1024);
    expect((JSON.parse(encoded) as unknown[]).length).toBeLessThan(40);
    vi.setSystemTime(Date.now() + 31 * 24 * 60 * 60 * 1000);
    expect(await new TelegramEmojiDeviceCache(storage).read(key + "39")).toBeNull();
    values.set("minishop_emoji_previews_v1", "invalid JSON");
    expect(await new TelegramEmojiDeviceCache(storage).read(key)).toBeNull();
  });
  it("invalidates both native and browser copies after an image decode failure", async () => {
    vi.useFakeTimers();
    const { storage } = device();
    const cache = new TelegramEmojiDeviceCache(storage);
    await cache.write(key, blob());
    await vi.advanceTimersByTimeAsync(40);
    const restored = (await cache.read(key))!;
    rejectEmojiPreviewBlob(restored);
    await vi.advanceTimersByTimeAsync(40);
    expect(await new TelegramEmojiDeviceCache(storage).read(key)).toBeNull();
  });
  it("times out unavailable native storage without blocking the network fallback", async () => {
    vi.useFakeTimers();
    const { storage } = device();
    storage.getItem = vi.fn();
    const result = new TelegramEmojiDeviceCache(storage).read(key);
    await vi.advanceTimersByTimeAsync(250);
    expect(await result).toBeNull();
  });
});
