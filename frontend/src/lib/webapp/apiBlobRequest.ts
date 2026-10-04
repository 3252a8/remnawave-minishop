import { currentBootSignal } from "./bootBudget";
import { requestSignal } from "./requestSignal";
import { EmojiMediaBlobCache, emojiMediaCacheTtl } from "./emojiMediaCache";
import type { ApiClient, MockApi } from "./publicApi";

type Options = {
  authenticatedHeaders: (options: RequestInit) => Headers;
  sessionScope: () => string;
  buildApiUrl: (path: string) => string;
  mockApi: MockApi | null;
  getMockContext: () => Parameters<MockApi>[2];
  onUnauthorized: () => void;
  requestTimeoutMs: number;
};

/** Keep binary exports/attachments unchanged; only authenticated emoji previews share data. */
export function createBlobRequester(config: Options): ApiClient["apiBlob"] {
  const cache = new EmojiMediaBlobCache();
  return async (path, options = {}) => {
    if (config.mockApi) {
      const value = await config.mockApi(path, options, config.getMockContext());
      if (typeof Blob !== "undefined" && value instanceof Blob) return value;
      if (typeof value === "string") return new Blob([value], { type: "text/csv;charset=utf-8" });
      throw new Error("mock_binary_response_unavailable");
    }
    const url = config.buildApiUrl(path);
    const headers = config.authenticatedHeaders(options);
    const session = config.sessionScope();
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
          throw payload;
        }
        return await response.blob();
      } finally {
        cleanup();
      }
    };
    if (!ttl) return request(consumerSignal);
    const key = JSON.stringify([url, session, [...headers]]);
    return cache.load(key, ttl, () => request(), consumerSignal);
  };
}
