import { isEmojiPreviewBlob } from "$lib/telegramEmoji/media";

const MAX_ITEMS = 32;
const MAX_ENCODED_BYTES = 6 * 1024 * 1024;
const PREVIEW_PATH = /^\/api\/admin\/telegram-emoji\/media\/([1-9][0-9]{0,19})\?v=([a-f0-9]{16})$/;
type Waiter = {
  url: string;
  resolve: (blob: Blob | null) => void;
  reject: (error: unknown) => void;
};
type Group = { waiters: Waiter[]; request: (path: string) => Promise<unknown> };

function decode(value: unknown, requested: Set<string>): Map<string, Blob> {
  const result = new Map<string, Blob>();
  if (
    !value ||
    typeof value !== "object" ||
    !("ok" in value) ||
    value.ok !== true ||
    !("previews" in value) ||
    !Array.isArray(value.previews) ||
    value.previews.length > MAX_ITEMS
  )
    return result;
  for (const item of value.previews as unknown[]) {
    if (
      !item ||
      typeof item !== "object" ||
      !("id" in item) ||
      !("version" in item) ||
      !("mime" in item) ||
      !("data" in item) ||
      typeof item.id !== "string" ||
      typeof item.version !== "string" ||
      typeof item.mime !== "string" ||
      typeof item.data !== "string"
    )
      continue;
    const url = `/api/admin/telegram-emoji/media/${item.id}?v=${item.version}`;
    if (!requested.has(url) || item.data.length > MAX_ENCODED_BYTES / 2) continue;
    try {
      const bytes = Uint8Array.from(atob(item.data), (character) => character.charCodeAt(0));
      const blob = new Blob([bytes], { type: item.mime });
      if (isEmojiPreviewBlob(blob)) result.set(url, blob);
    } catch {
      /* A malformed preview falls back to its individually validated endpoint. */
    }
  }
  return result;
}

/** One authenticated request per visible group, instead of one round-trip per glyph. */
export class EmojiPreviewBatch {
  private groups = new Map<string, Group>();

  load(url: string, scope: string, request: Group["request"]): Promise<Blob | null> {
    if (!PREVIEW_PATH.test(url)) return Promise.resolve(null);
    return new Promise((resolve, reject) => {
      let group = this.groups.get(scope);
      if (!group) {
        const created: Group = { waiters: [], request };
        group = created;
        this.groups.set(scope, created);
        setTimeout(() => {
          if (this.groups.get(scope) === created) this.flush(scope, created);
        }, 8);
      }
      group.waiters.push({ url, resolve, reject });
      if (group.waiters.length >= MAX_ITEMS) this.flush(scope, group);
    });
  }

  private flush(scope: string, group: Group): void {
    this.groups.delete(scope);
    const requested = new Set(group.waiters.map((waiter) => waiter.url));
    const refs = [...requested].map((url) => {
      const match = PREVIEW_PATH.exec(url);
      return `${match?.[1]}:${match?.[2]}`;
    });
    const path = `/api/admin/telegram-emoji/previews?items=${encodeURIComponent(refs.join(","))}`;
    void group
      .request(path)
      .then((payload) => {
        const previews = decode(payload, requested);
        for (const waiter of group.waiters) waiter.resolve(previews.get(waiter.url) || null);
      })
      .catch((error: unknown) => {
        const status = error && typeof error === "object" && "status" in error ? error.status : 0;
        for (const waiter of group.waiters) {
          if (status === 404 || status === 405)
            waiter.resolve(null); // Older servers still work.
          else waiter.reject(error); // Never turn an outage or rate limit into 32 more requests.
        }
      });
  }
}
