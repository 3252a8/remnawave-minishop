import { isCustomEmojiId } from "./customEmoji.js";
import type { CustomEmojiMediaLoader } from "./types.js";
import { isEmojiPreviewBlob, rejectEmojiPreviewBlob } from "$lib/telegramEmoji/media";

type ThumbnailTarget = { show: (url: string) => void; clear: () => void; loading?: () => void };

/** Own an authenticated request and its blob URL outside the message document. */
export class CustomEmojiMedia {
  private sequence = 0;
  private controller: AbortController | null = null;
  private url = "";
  private blob: Blob | null = null;
  private destroyed = false;

  constructor(
    private loadMedia: CustomEmojiMediaLoader,
    private target: ThumbnailTarget
  ) {}

  clear(): void {
    this.sequence += 1;
    this.controller?.abort();
    this.controller = null;
    this.target.clear();
    if (this.url) URL.revokeObjectURL(this.url);
    this.url = "";
    this.blob = null;
  }

  fail(): void {
    if (this.blob) rejectEmojiPreviewBlob(this.blob);
    this.clear();
  }

  async load(id: string): Promise<void> {
    this.clear();
    if (this.destroyed || !isCustomEmojiId(id)) return;
    this.target.loading?.();
    const sequence = this.sequence;
    const controller = new AbortController();
    this.controller = controller;
    try {
      const blob = await this.loadMedia(id, controller.signal);
      if (controller.signal.aborted || sequence !== this.sequence || this.destroyed) return;
      // SVG/HTML and oversized or empty bodies never become image URLs.
      if (!isEmojiPreviewBlob(blob)) {
        this.clear();
        return;
      }
      this.blob = blob;
      this.url = URL.createObjectURL(blob);
      this.target.show(this.url);
    } catch {
      if (!controller.signal.aborted && sequence === this.sequence) this.clear();
    }
  }

  destroy(): void {
    this.destroyed = true;
    this.clear();
  }
}
