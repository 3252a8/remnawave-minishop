import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getSchema } from "@tiptap/core";

import { CustomEmojiNodeViewMedia } from "./customEmojiNodeView";
import { composerExtensions } from "./editorSchema";
import { type Doc, docToTelegramHtml, telegramHtmlToDoc } from "./telegramHtml";
import type { CustomEmojiMediaLoader } from "./types";

const id = "5368324170671202286";
const png = () => new Blob(["image bytes"], { type: "image/png" });

describe("custom emoji node view media", () => {
  beforeEach(() => {
    let nextUrl = 0;
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:emoji-${++nextUrl}`);
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  });
  afterEach(() => vi.restoreAllMocks());

  it("loads the exact string ID through the host and releases the URL on destruction", async () => {
    const loader = vi.fn<CustomEmojiMediaLoader>().mockResolvedValue(png());
    const target = { show: vi.fn(), clear: vi.fn() };
    const media = new CustomEmojiNodeViewMedia(loader, target);
    await media.load(id);
    expect(loader).toHaveBeenCalledWith(id, expect.any(AbortSignal));
    expect(target.show).toHaveBeenCalledWith("blob:emoji-1");
    media.destroy();
    expect(loader.mock.calls[0]?.[1].aborted).toBe(true);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith("blob:emoji-1");
    await media.load(id);
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("aborts an old request and ignores its late response when the node changes", async () => {
    let completeFirst: ((blob: Blob) => void) | undefined;
    const loader = vi
      .fn<CustomEmojiMediaLoader>()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            completeFirst = resolve;
          })
      )
      .mockResolvedValue(png());
    const target = { show: vi.fn(), clear: vi.fn() };
    const media = new CustomEmojiNodeViewMedia(loader, target);
    const old = media.load(id);
    await media.load("5368324170671202287");
    expect(loader.mock.calls[0]?.[1].aborted).toBe(true);
    completeFirst?.(png());
    await old;
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(target.show).toHaveBeenCalledExactlyOnceWith("blob:emoji-1");
    media.destroy();
  });

  it("does not allocate a blob URL if the editor closes while loading", async () => {
    let complete: ((blob: Blob) => void) | undefined;
    const loader = vi.fn<CustomEmojiMediaLoader>().mockImplementation(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        })
    );
    const target = { show: vi.fn(), clear: vi.fn() };
    const media = new CustomEmojiNodeViewMedia(loader, target);
    const loading = media.load(id);
    media.destroy();
    complete?.(png());
    await loading;
    expect(loader.mock.calls[0]?.[1].aborted).toBe(true);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(target.show).not.toHaveBeenCalled();
  });

  it("keeps fallback on an authenticated request failure and discards the previous URL", async () => {
    const loader = vi
      .fn<CustomEmojiMediaLoader>()
      .mockResolvedValueOnce(png())
      .mockRejectedValue(new Error("Unauthorized"));
    const target = { show: vi.fn(), clear: vi.fn() };
    const media = new CustomEmojiNodeViewMedia(loader, target);
    await media.load(id);
    await media.load("5368324170671202287");
    expect(target.show).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith("blob:emoji-1");
    expect(target.clear).toHaveBeenCalledTimes(3);
    media.destroy();
  });

  it.each([
    new Blob(["<script>alert(1)</script>"], { type: "text/html" }),
    new Blob(["<svg onload='alert(1)'/>"], { type: "image/svg+xml" }),
    new Blob([], { type: "image/png" }),
    new Blob([new Uint8Array(2 * 1024 * 1024 + 1)], { type: "image/png" }),
  ])("never renders an unsafe, empty or oversized media body", async (blob) => {
    const target = { show: vi.fn(), clear: vi.fn() };
    const media = new CustomEmojiNodeViewMedia(
      vi.fn<CustomEmojiMediaLoader>().mockResolvedValue(blob),
      target
    );
    await media.load(id);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(target.show).not.toHaveBeenCalled();
    media.destroy();
  });

  it("restores fallback and revokes the URL when image decoding fails", async () => {
    const target = { show: vi.fn(), clear: vi.fn() };
    const media = new CustomEmojiNodeViewMedia(
      vi.fn<CustomEmojiMediaLoader>().mockResolvedValue(png()),
      target
    );
    await media.load(id);
    media.clear();
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith("blob:emoji-1");
    expect(target.clear).toHaveBeenCalledTimes(2);
    media.destroy();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  });

  it.each(["", "-1", "0", "5368324170671202286/../../secret", '1" onclick="alert(1)'])(
    "never calls a host loader for an invalid entity ID: %s",
    async (invalid) => {
      const loader = vi.fn<CustomEmojiMediaLoader>().mockResolvedValue(png());
      const media = new CustomEmojiNodeViewMedia(loader, { show: vi.fn(), clear: vi.fn() });
      await media.load(invalid);
      expect(loader).not.toHaveBeenCalled();
      media.destroy();
    }
  );

  it("keeps media outside the atom, clipboard and source when a loader is configured", () => {
    const loader = vi.fn<CustomEmojiMediaLoader>().mockResolvedValue(png());
    const schema = getSchema(composerExtensions("", { loadCustomEmojiMedia: loader }));
    const source = `<b><tg-emoji emoji-id="${id}">👩🏽‍💻</tg-emoji></b>`;
    const document = schema.nodeFromJSON(telegramHtmlToDoc(source));
    const node = document.nodeAt(1);
    expect(node?.isAtom).toBe(true);
    expect(node?.attrs).toEqual({ id, fallback: "👩🏽‍💻" });
    expect(node && schema.nodes.customEmoji.spec.toDOM?.(node)).toEqual([
      "span",
      { class: "rt-custom-emoji", "data-custom-emoji-id": id },
      "👩🏽‍💻",
    ]);
    expect(docToTelegramHtml(document.toJSON() as Doc)).toBe(source);
    expect(loader).not.toHaveBeenCalled();
    expect(JSON.stringify(document.toJSON())).not.toContain("blob:");
  });
});
