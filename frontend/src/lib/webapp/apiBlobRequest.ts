import { currentBootSignal } from "./bootBudget";
import { requestSignal } from "./requestSignal";
import { EmojiMediaBlobCache, emojiMediaCacheTtl } from "./emojiMediaCache";
import { EmojiPreviewBatch } from "./emojiPreviewBatch";
import { persistentEmojiKey, readEmojiPreview, writeEmojiPreview } from "./emojiPreviewStorage";
import type { ApiClient, MockApi } from "./publicApi";
import { catalogEmojiPreviewUrl } from "./emojiCatalogStorage";

type Options = {
  authenticatedHeaders: (options: RequestInit) => Headers;
  sessionScope: () => string;
  persistentScope: () => string;
  buildApiUrl: (path: string) => string;
  mockApi: MockApi | null;
  getMockContext: () => Parameters<MockApi>[2];
  onUnauthorized: () => void;
  requestTimeoutMs: number;
};

/** Keep binary exports/attachments unchanged; only authenticated emoji previews share data. */
export function createBlobRequester(config: Options): ApiClient["apiBlob"] {
  const cache = new EmojiMediaBlobCache();
  const batches = new EmojiPreviewBatch();
  const transient = new WeakSet<Blob>();
  return async (path, options = {}) => {
    if (config.mockApi) {
      const value = await config.mockApi(path, options, config.getMockContext());
      if (typeof Blob !== "undefined" && value instanceof Blob) return value;
      if (typeof value === "string") return new Blob([value], { type: "text/csv;charset=utf-8" });
      throw new Error("mock_binary_response_unavailable");
    }
    let url = config.buildApiUrl(path);
    const headers = config.authenticatedHeaders(options);
    const session = config.sessionScope();
    const scope = config.persistentScope();
    const unversioned = /^\/api\/admin\/telegram-emoji\/media\/([1-9][0-9]{0,19})$/.exec(url);
    if (
      unversioned &&
      (headers.get("Authorization") || session) &&
      !options.body &&
      String(options.method || "GET").toUpperCase() === "GET" &&
      options.cache !== "no-store"
    ) {
      url = (await catalogEmojiPreviewUrl(scope, unversioned[1])) || url;
      if (config.persistentScope() !== scope)
        throw new DOMException("The session changed", "AbortError");
    }
    const ttl =
      String(options.method || "GET").toUpperCase() === "GET" &&
      !options.body &&
      (headers.get("Authorization") || session) &&
      options.cache !== "no-store"
        ? emojiMediaCacheTtl(url)
        : 0;
    const consumerSignal = options.signal || currentBootSignal();
    const request = async (parentSignal?: AbortSignal | null): Promise<Blob> => {
      const { signal, cleanup } = requestSignal(parentSignal, config.requestTimeoutMs);
      try {
        const response = await fetch(url, {
          cache: ttl ? "default" : "no-store",
          ...options,
          headers,
          credentials: "same-origin",
          signal,
        });
        if (response.status === 401) config.onUnauthorized();
        if (!response.ok) {
          const payload = await response.json().catch(() => ({
            ok: false,
            error: "image_load_failed",
            status: response.status,
          }));
          throw { ...payload, status: response.status };
        }
        const blob = await response.blob();
        if (ttl && /no-cache|no-store/.test(response.headers?.get("Cache-Control") || ""))
          transient.add(blob);
        return blob;
      } finally {
        cleanup();
      }
    };
    if (!ttl) return request(consumerSignal);
    const key = JSON.stringify([url, scope, session, [...headers]]);
    const storedKey = persistentEmojiKey(scope, url);
    return cache.load(
      key,
      ttl,
      async () => {
        if (!storedKey) return request();
        const stillAuthorized = () =>
          config.persistentScope() === scope &&
          Boolean(
            config.authenticatedHeaders(options).get("Authorization") || config.sessionScope()
          );
        const stored = await readEmojiPreview(scope, url);
        if (!stillAuthorized()) throw new DOMException("The session changed", "AbortError");
        if (stored) return stored;
        const batched = await batches.load(
          url,
          JSON.stringify([scope, session, [...headers]]),
          async (path) => {
            const { signal, cleanup } = requestSignal(null, config.requestTimeoutMs);
            try {
              const response = await fetch(path, {
                headers,
                credentials: "same-origin",
                cache: "no-store",
                signal,
              });
              if (response.status === 401) config.onUnauthorized();
              if (!response.ok) throw { status: response.status };
              if (Number(response.headers.get("Content-Length") || "0") > 6 * 1024 * 1024)
                throw new Error("emoji_preview_batch_too_large");
              const text = await response.text();
              if (text.length > 6 * 1024 * 1024) throw new Error("emoji_preview_batch_too_large");
              return JSON.parse(text) as unknown;
            } finally {
              cleanup();
            }
          }
        );
        const blob = batched || (await request());
        if (!stillAuthorized()) throw new DOMException("The session changed", "AbortError");
        if (stillAuthorized() && !transient.has(blob)) await writeEmojiPreview(scope, url, blob);
        return blob;
      },
      consumerSignal,
      (blob) => !transient.has(blob)
    );
  };
}
