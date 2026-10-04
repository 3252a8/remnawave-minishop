import { afterEach, describe, expect, it, vi } from "vitest";
import { EmojiPreviewBatch } from "./emojiPreviewBatch";

afterEach(() => vi.useRealTimers());
const version = "0123456789abcdef";
const path = (id: number) => `/api/admin/telegram-emoji/media/${id}?v=${version}`;
const payload = (ids: number[]) => ({
  ok: true,
  previews: ids.map((id) => ({
    id: String(id),
    version,
    mime: "image/png",
    data: btoa("preview"),
  })),
});

describe("disk preview batches", () => {
  it("loads 96 visible previews in three bounded requests", async () => {
    vi.useFakeTimers();
    const request = vi.fn(async (url: string) =>
      payload(
        new URL(url, "https://example.test").searchParams
          .get("items")!
          .split(",")
          .map((item) => Number(item.split(":")[0]))
      )
    );
    const batch = new EmojiPreviewBatch();
    const pending = Array.from({ length: 96 }, (_, index) =>
      batch.load(path(index + 1), "account-a", request)
    );
    await vi.runAllTimersAsync();
    const blobs = await Promise.all(pending);
    expect(request).toHaveBeenCalledTimes(3);
    expect(blobs.every((blob) => blob?.type === "image/png")).toBe(true);
  });
  it("separates authenticated contexts and accepts only requested versions", async () => {
    vi.useFakeTimers();
    const request = vi.fn(async () => ({
      ok: true,
      previews: [
        ...payload([1, 2]).previews,
        { id: "3", version: "0000000000000000", mime: "image/png", data: btoa("wrong") },
        { id: "4", version, mime: "image/svg+xml", data: btoa("unsafe") },
      ],
    }));
    const batch = new EmojiPreviewBatch();
    const pending = [
      batch.load(path(1), "a", request),
      batch.load(path(2), "b", request),
      batch.load(path(3), "a", request),
      batch.load(path(4), "a", request),
    ];
    await vi.runAllTimersAsync();
    const [one, two, three, four] = await Promise.all(pending);
    expect(one).toBeInstanceOf(Blob);
    expect(two).toBeInstanceOf(Blob);
    expect(three).toBeNull();
    expect(four).toBeNull();
    expect(request).toHaveBeenCalledTimes(2);
  });
  it.each([404, 405])(
    "falls back to individual previews when the batch endpoint returns %s",
    async (status) => {
      vi.useFakeTimers();
      const pending = new EmojiPreviewBatch().load(path(1), "a", async () => {
        throw { status };
      });
      await vi.runAllTimersAsync();
      expect(await pending).toBeNull();
    }
  );
  it.each([401, 403, 429, 503])(
    "never amplifies a rejected batch into individual requests (%s)",
    async (status) => {
      vi.useFakeTimers();
      const pending = new EmojiPreviewBatch().load(path(1), "a", async () => {
        throw { status };
      });
      const rejected = expect(pending).rejects.toEqual({ status });
      await vi.runAllTimersAsync();
      await rejected;
    }
  );
});
