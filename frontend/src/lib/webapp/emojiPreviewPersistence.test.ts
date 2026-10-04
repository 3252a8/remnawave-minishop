import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "./publicApi";
import { persistentEmojiKey, readEmojiPreview, writeEmojiPreview } from "./emojiPreviewStorage";

const storage = vi.hoisted(() => new Map<string, Blob>());
vi.mock("./emojiPreviewStorage", async (importOriginal) => {
  const original = await importOriginal<typeof import("./emojiPreviewStorage")>();
  return {
    ...original,
    readEmojiPreview: vi.fn(
      async (scope: string, url: string) => storage.get(JSON.stringify([scope, url])) || null
    ),
    writeEmojiPreview: vi.fn(async (scope: string, url: string, blob: Blob) => {
      storage.set(JSON.stringify([scope, url]), blob);
    }),
  };
});
const url = "/api/admin/telegram-emoji/media/5368651601797984900?v=0123456789abcdef";
beforeEach(() => {
  storage.clear();
  vi.clearAllMocks();
});
afterEach(() => vi.unstubAllGlobals());

describe("preview persistence across miniapp sessions", () => {
  it("reuses the same account preview after recreating the API client and rotating credentials", async () => {
    const blob = new Blob(["image"], { type: "image/png" });
    storage.set(JSON.stringify(["42", url]), blob);
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const first = createApiClient({
      getAuthToken: () => "old-token",
      getEmojiCacheScope: () => "42",
    });
    const reopened = createApiClient({
      getAuthToken: () => "new-token",
      getCsrfToken: () => "new-cookie",
      getEmojiCacheScope: () => "42",
    });
    expect(await first.apiBlob(url)).toBe(blob);
    expect(await reopened.apiBlob(url)).toBe(blob);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("does not reuse another account or an obsolete version", async () => {
    storage.set(JSON.stringify(["42", url]), new Blob(["old"], { type: "image/png" }));
    const fetchMock = vi.fn(async () => Response.json({ ok: true, previews: [] }));
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation(async (requestUrl?: unknown) =>
      typeof requestUrl === "string" && requestUrl.includes("/previews?")
        ? Response.json({ ok: true, previews: [] })
        : new Response(new Blob(["new"], { type: "image/png" }))
    );
    const client = createApiClient({ getAuthToken: () => "token", getEmojiCacheScope: () => "43" });
    expect(await (await client.apiBlob(url)).text()).toBe("new");
    expect(writeEmojiPreview).toHaveBeenCalledWith("43", url, expect.any(Blob));
    expect(readEmojiPreview).toHaveBeenCalledWith("43", url);
    expect(persistentEmojiKey("42", url.replace("0123456789abcdef", "0000000000000001"))).not.toBe(
      persistentEmojiKey("42", url)
    );
  });
  it("keeps unversioned ticket images and anonymous clients out of disk persistence", async () => {
    const fetchMock = vi.fn(async () => new Response(new Blob(["image"], { type: "image/png" })));
    vi.stubGlobal("fetch", fetchMock);
    await createApiClient({ getAuthToken: () => "token", getEmojiCacheScope: () => "42" }).apiBlob(
      "/api/support/tickets/7/emoji/5368651601797984900"
    );
    await createApiClient({ getEmojiCacheScope: () => "42" }).apiBlob(url);
    expect(readEmojiPreview).not.toHaveBeenCalled();
    expect(writeEmojiPreview).not.toHaveBeenCalled();
  });
  it("does not persist a response after the account changes during its load", async () => {
    let scope = "42";
    const fetchMock = vi.fn(async () => {
      scope = "43";
      return Response.json({
        ok: true,
        previews: [
          {
            id: "5368651601797984900",
            version: "0123456789abcdef",
            mime: "image/png",
            data: btoa("image"),
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(
      createApiClient({ getAuthToken: () => "token", getEmojiCacheScope: () => scope }).apiBlob(url)
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(writeEmojiPreview).not.toHaveBeenCalled();
  });

  it("does not retain a stale version when the server requires revalidation", async () => {
    const fetchMock = vi.fn(async (requestUrl: unknown) =>
      typeof requestUrl === "string" && requestUrl.includes("/previews?")
        ? Response.json({ ok: true, previews: [] })
        : new Response("image", {
            headers: { "Content-Type": "image/png", "Cache-Control": "private, no-cache" },
          })
    );
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient({ getAuthToken: () => "token", getEmojiCacheScope: () => "42" });
    await client.apiBlob(url);
    await client.apiBlob(url);
    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(writeEmojiPreview).not.toHaveBeenCalled();
  });
});
