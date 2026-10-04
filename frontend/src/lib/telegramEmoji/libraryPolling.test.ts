import { afterEach, describe, expect, it, vi } from "vitest";
import { emojiLibraryIsWarming, pollEmojiLibrary } from "./libraryPolling";
import type { TelegramEmojiApi } from "./api";
import type { EmojiLibrary } from "./types";
import { buildTelegramEmojiMediaUrlPath } from "./paths";

function library(state: EmojiLibrary["sets"][number]["state"], cached = 0): EmojiLibrary {
  return {
    library: { schema_version: 1, sets: ["pack"], manual_ids: [] },
    revision: "same-revision",
    sets: [
      { name: "pack", title: "Pack", count: 6, state, cached_count: cached, preview_count: 5 },
    ],
  };
}
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe("emoji library progress polling", () => {
  it("reports progress and stops on partial rather than polling endlessly", async () => {
    vi.useFakeTimers();
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, ...library("warming", 2) })
      .mockResolvedValue({ ok: true, ...library("partial", 4) });
    const update = vi.fn();
    const error = vi.fn();
    const stop = pollEmojiLibrary(api as unknown as TelegramEmojiApi, update, error);
    await vi.advanceTimersByTimeAsync(2000);
    expect(update).toHaveBeenLastCalledWith(expect.objectContaining(library("warming", 2)));
    await vi.advanceTimersByTimeAsync(2000);
    expect(update).toHaveBeenLastCalledWith(expect.objectContaining(library("partial", 4)));
    await vi.advanceTimersByTimeAsync(6000);
    expect(api).toHaveBeenCalledTimes(2);
    expect(error).not.toHaveBeenCalled();
    stop();
  });

  it("cancels pending work and ignores a late response when the panel closes", async () => {
    vi.useFakeTimers();
    let complete: ((value: unknown) => void) | undefined;
    const api = vi.fn(
      (_path: string, _options: RequestInit) =>
        new Promise((resolve) => {
          complete = resolve;
        })
    );
    const update = vi.fn();
    const error = vi.fn();
    const stop = pollEmojiLibrary(api as unknown as TelegramEmojiApi, update, error);
    await vi.advanceTimersByTimeAsync(2000);
    stop();
    expect(api.mock.calls[0][1].signal?.aborted).toBe(true);
    complete?.({ ok: true, ...library("ready", 5) });
    await vi.advanceTimersByTimeAsync(6000);
    expect(api).toHaveBeenCalledTimes(1);
    expect(update).not.toHaveBeenCalled();
    expect(error).not.toHaveBeenCalled();
  });

  it("recovers from a transient request failure and stops when ready", async () => {
    vi.useFakeTimers();
    const api = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({ ok: true, ...library("ready", 5) });
    const update = vi.fn();
    const error = vi.fn();
    const stop = pollEmojiLibrary(api as unknown as TelegramEmojiApi, update, error);
    await vi.advanceTimersByTimeAsync(6000);
    expect(error).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith(expect.objectContaining(library("ready", 5)));
    await vi.advanceTimersByTimeAsync(6000);
    expect(api).toHaveBeenCalledTimes(2);
    stop();
  });

  it("backs off repeated outages to thirty seconds and resets after recovery", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(0);
    let offline = true;
    const calls: number[] = [];
    const api = vi.fn(async () => {
      calls.push(Date.now());
      if (offline) throw new Error("offline");
      return { ok: true, ...library("warming", 2) };
    });
    const stop = pollEmojiLibrary(api as unknown as TelegramEmojiApi, vi.fn(), vi.fn());
    await vi.advanceTimersByTimeAsync(60000);
    expect(calls).toEqual([2000, 6000, 14000, 30000, 60000]);
    offline = false;
    await vi.advanceTimersByTimeAsync(30000);
    offline = true;
    await vi.advanceTimersByTimeAsync(6000);
    expect(calls).toEqual([2000, 6000, 14000, 30000, 60000, 90000, 92000, 96000]);
    stop();
  });

  it("does not request after closing before the timer or for completed/unknown states", async () => {
    vi.useFakeTimers();
    const api = vi.fn();
    pollEmojiLibrary(api as unknown as TelegramEmojiApi, vi.fn(), vi.fn())();
    await vi.advanceTimersByTimeAsync(6000);
    expect(api).not.toHaveBeenCalled();
    for (const state of ["ready", "partial", "error", "unknown"] as const)
      expect(emojiLibraryIsWarming(library(state))).toBe(false);
    expect(emojiLibraryIsWarming(library("warming"))).toBe(true);
    expect(emojiLibraryIsWarming(null)).toBe(false);
  });

  it("preserves catalog versions and rejects external or forged media URLs", () => {
    const url = "/api/admin/telegram-emoji/media/5368324170671202286?v=0123456789abcdef";
    expect(buildTelegramEmojiMediaUrlPath(url)).toBe(url);
    for (const source of [
      "https://evil.test/image",
      "/api/admin/telegram-emoji/media/0",
      `${url}&extra=1`,
      '/api/admin/telegram-emoji/media/1" onerror="alert(1)',
    ])
      expect(buildTelegramEmojiMediaUrlPath(source)).toBeNull();
  });
});
