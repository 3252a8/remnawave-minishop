import { describe, expect, it, vi } from "vitest";
import { EmojiMediaBlobCache, emojiMediaCacheTtl } from "./emojiMediaCache";
import { rejectEmojiPreviewBlob } from "$lib/telegramEmoji/media";

const preview = (size = 3) => new Blob([new Uint8Array(size)], { type: "image/png" });

describe("emoji media Blob LRU", () => {
  it("limits both bytes and entry count while preserving recently used previews", async () => {
    for (const cache of [new EmojiMediaBlobCache(6, 512), new EmojiMediaBlobCache(1024, 2)]) {
      const loader = vi.fn(async (_key: string) => preview());
      const load = (key: string) => cache.load(key, 1000, () => loader(key));
      await load("a");
      await load("b");
      await load("a");
      await load("c");
      await load("b");
      expect(loader.mock.calls.map(([key]) => key)).toEqual(["a", "b", "c", "b"]);
    }
  });

  it("expires entries and refuses media exceeding the byte budget", async () => {
    let now = 0;
    const cache = new EmojiMediaBlobCache(6, 2, () => now);
    const loader = vi.fn(async () => preview());
    await cache.load("a", 100, loader);
    now = 99;
    await cache.load("a", 100, loader);
    now = 100;
    await cache.load("a", 100, loader);
    expect(loader).toHaveBeenCalledTimes(2);
    const large = vi.fn(async () => preview(7));
    await cache.load("large", 100, large);
    await cache.load("large", 100, large);
    expect(large).toHaveBeenCalledTimes(2);
  });

  it("retries decode failures and unsafe media without negative caching", async () => {
    const cache = new EmojiMediaBlobCache();
    const bad = preview();
    const good = preview();
    const loader = vi.fn().mockResolvedValueOnce(bad).mockResolvedValue(good);
    expect(await cache.load("same", 1000, loader)).toBe(bad);
    rejectEmojiPreviewBlob(bad);
    expect(await cache.load("same", 1000, loader)).toBe(good);
    expect(loader).toHaveBeenCalledTimes(2);
    const unsafe = vi.fn(async () => new Blob(["<svg/>"], { type: "image/svg+xml" }));
    await cache.load("unsafe", 1000, unsafe);
    await cache.load("unsafe", 1000, unsafe);
    expect(unsafe).toHaveBeenCalledTimes(2);
  });

  it("allows only the two emoji routes and strict optional version queries", () => {
    expect(emojiMediaCacheTtl("/api/admin/telegram-emoji/media/5368324170671202286")).toBe(300000);
    expect(
      emojiMediaCacheTtl("/api/support/tickets/7/emoji/5368324170671202286?v=0123456789abcdef")
    ).toBe(86400000);
    for (const path of [
      "/api/admin/payments/export.csv",
      "/api/support/images/7",
      "/api/admin/telegram-emoji/media/0",
      "/api/admin/telegram-emoji/media/1?v=invalid",
      "/api/admin/telegram-emoji/media/1?url=https://evil.test",
      "https://evil.test/api/admin/telegram-emoji/media/1",
    ])
      expect(emojiMediaCacheTtl(path)).toBe(0);
  });
});
