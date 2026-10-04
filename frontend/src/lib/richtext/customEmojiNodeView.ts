import type { NodeViewRenderer } from "@tiptap/core";

import { isCustomEmoji } from "./customEmoji.js";
import { CustomEmojiMedia } from "./customEmojiMedia.js";
import type { CustomEmojiMediaLoader } from "./types.js";

/** DOM-only presentation. The extension's renderHTML still owns clipboard/source output. */
export function createCustomEmojiNodeView(loadMedia: CustomEmojiMediaLoader): NodeViewRenderer {
  return ({ node }) => {
    const dom = document.createElement("span");
    dom.className = "rt-custom-emoji";
    dom.contentEditable = "false";
    dom.style.display = "inline-grid";
    dom.style.width = dom.style.height = "1.35em";
    dom.style.verticalAlign = "middle";
    dom.style.placeItems = "center";
    const fallback = document.createElement("span");
    fallback.style.gridArea = "1 / 1";
    const image = document.createElement("img");
    image.alt = "";
    image.draggable = false;
    // The wrapper's observer owns lazy loading; a hidden lazy img can never intersect.
    image.decoding = "async";
    image.hidden = true;
    image.style.gridArea = "1 / 1";
    image.style.width = image.style.height = "100%";
    image.style.objectFit = "contain";
    dom.append(fallback, image);

    let current = node;
    let destroyed = false;
    let visible = typeof IntersectionObserver === "undefined";
    let observer: IntersectionObserver | null = null;
    const media = new CustomEmojiMedia(loadMedia, {
      clear: () => {
        image.onload = image.onerror = null;
        image.hidden = true;
        image.removeAttribute("src");
        fallback.style.opacity = "";
      },
      show: (url) => {
        image.onload = () => {
          if (destroyed || image.getAttribute("src") !== url) return;
          image.hidden = false;
          fallback.style.opacity = "0";
        };
        image.onerror = () => media.clear();
        image.src = url;
      },
    });

    const attrs = () => ({
      id: String(current.attrs.id || ""),
      fallback: String(current.attrs.fallback || ""),
    });
    const load = () => {
      const emoji = attrs();
      if (visible && !destroyed && isCustomEmoji(emoji)) void media.load(emoji.id);
    };
    const syncFallback = () => {
      const emoji = attrs();
      fallback.textContent = emoji.fallback;
      dom.setAttribute("data-custom-emoji-id", emoji.id);
    };
    syncFallback();
    if (!visible) {
      observer = new IntersectionObserver(
        (entries) => {
          if (destroyed || !entries.some((entry) => entry.isIntersecting)) return;
          visible = true;
          observer?.disconnect();
          observer = null;
          load();
        },
        { rootMargin: "100px" }
      );
      observer.observe(dom);
    } else load();

    return {
      dom,
      update(next) {
        if (next.type !== current.type) return false;
        const changedId = next.attrs.id !== current.attrs.id;
        const changedFallback = next.attrs.fallback !== current.attrs.fallback;
        current = next;
        syncFallback();
        if (changedId || changedFallback) {
          media.clear();
          load();
        }
        return true;
      },
      selectNode: () => dom.classList.add("ProseMirror-selectednode"),
      deselectNode: () => dom.classList.remove("ProseMirror-selectednode"),
      ignoreMutation: (mutation) => mutation.type !== "selection",
      destroy() {
        destroyed = true;
        observer?.disconnect();
        observer = null;
        media.destroy();
      },
    };
  };
}
