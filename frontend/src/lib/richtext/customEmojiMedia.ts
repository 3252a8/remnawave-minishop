import { isCustomEmojiId } from "./customEmoji.js";
import type { CustomEmojiMediaLoader } from "./types.js";

type ThumbnailTarget = { show: (url: string) => void; clear: () => void };

/** Own an authenticated request and its blob URL outside the message document. */
export class CustomEmojiMedia {
  private sequence = 0;
  private controller: AbortController | null = null;
  private url = "";
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
  }

  async load(id: string): Promise<void> {
    this.clear();
    if (this.destroyed || !isCustomEmojiId(id)) return;
    const sequence = this.sequence;
    const controller = new AbortController();
    this.controller = controller;
    try {
      const blob = await this.loadMedia(id, controller.signal);
      if (controller.signal.aborted || sequence !== this.sequence || this.destroyed) return;
      // SVG/HTML and oversized or empty bodies never become image URLs.
      if (
        !/^image\/(png|webp|jpeg|gif)$/i.test(blob.type) ||
        blob.size === 0 ||
        blob.size > 2 * 1024 * 1024
      )
        return;
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
