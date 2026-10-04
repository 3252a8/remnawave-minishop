import { isEmojiPreviewBlob } from "$lib/telegramEmoji/media";

const VERSIONED_TTL = 24 * 60 * 60 * 1000;
const UNVERSIONED_TTL = 5 * 60 * 1000;

/** No other binary API, extra query parameter or external URL enters this cache. */
export function emojiMediaCacheTtl(url: string): number {
  const match =
    /^\/api\/(?:admin\/telegram-emoji\/media\/[1-9][0-9]{0,19}|support\/tickets\/[1-9][0-9]*\/emoji\/[1-9][0-9]{0,19})(\?v=[a-f0-9]{16})?$/.exec(
      url
    );
  return match ? (match[1] ? VERSIONED_TTL : UNVERSIONED_TTL) : 0;
}

function waitForConsumer(promise: Promise<Blob>, signal?: AbortSignal | null): Promise<Blob> {
  if (!signal) return promise;
  return new Promise((resolve, reject) => {
    const abort = () => {
      signal.removeEventListener("abort", abort);
      reject(signal.reason || new DOMException("The request was aborted", "AbortError"));
    };
    if (signal.aborted) return abort();
    signal.addEventListener("abort", abort, { once: true });
    void promise.then(
      (blob) => {
        signal.removeEventListener("abort", abort);
        resolve(blob);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", abort);
        reject(error);
      }
    );
  });
}

type CachedBlob = { blob: Blob; expires: number };

/** Per-client LRU; keys include full URL and the current authenticated session. */
export class EmojiMediaBlobCache {
  private entries = new Map<string, CachedBlob>();
  private pending = new Map<string, Promise<Blob>>();
  private bytes = 0;

  constructor(
    private maxBytes = 16 * 1024 * 1024,
    private maxEntries = 512,
    private now = () => Date.now()
  ) {}

  private remove(key: string): void {
    const entry = this.entries.get(key);
    if (entry) this.bytes -= entry.blob.size;
    this.entries.delete(key);
  }

  private remember(key: string, blob: Blob, ttl: number): void {
    if (!isEmojiPreviewBlob(blob) || blob.size > this.maxBytes || this.maxEntries < 1) return;
    this.remove(key);
    this.entries.set(key, { blob, expires: this.now() + ttl });
    this.bytes += blob.size;
    while (this.bytes > this.maxBytes || this.entries.size > this.maxEntries) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.remove(oldest);
    }
  }

  load(
    key: string,
    ttl: number,
    load: () => Promise<Blob>,
    signal?: AbortSignal | null,
    cacheable: (blob: Blob) => boolean = () => true
  ): Promise<Blob> {
    if (signal?.aborted)
      return Promise.reject(
        signal.reason || new DOMException("The request was aborted", "AbortError")
      );
    const cached = this.entries.get(key);
    if (cached && cached.expires > this.now() && isEmojiPreviewBlob(cached.blob)) {
      this.entries.delete(key);
      this.entries.set(key, cached);
      return waitForConsumer(Promise.resolve(cached.blob), signal);
    }
    this.remove(key);
    let pending = this.pending.get(key);
    if (!pending) {
      pending = Promise.resolve()
        .then(load)
        .then((blob) => {
          if (cacheable(blob)) this.remember(key, blob, ttl);
          return blob;
        })
        .finally(() => this.pending.delete(key));
      this.pending.set(key, pending);
    }
    // Consumer cancellation never aborts a shared request or removes its warm result.
    return waitForConsumer(pending, signal);
  }
}
