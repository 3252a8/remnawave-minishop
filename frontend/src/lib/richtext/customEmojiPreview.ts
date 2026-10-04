import type { Attachment } from "svelte/attachments";

import { isCustomEmoji } from "./customEmoji.js";
import { CustomEmojiMedia } from "./customEmojiMedia.js";
import type { CustomEmojiMediaLoader } from "./types.js";

/** Decorate only the canonical placeholders produced by messageDisplayHtml. */
export function mountCustomEmojiPreviews(
  element: HTMLElement,
  loadMedia: CustomEmojiMediaLoader
): () => void {
  const cleanups: Array<() => void> = [];
  for (const wrapper of element.querySelectorAll<HTMLElement>(
    "span.rt-custom-emoji[data-custom-emoji-id]"
  )) {
    const fallback = wrapper.firstElementChild;
    const emoji = {
      id: wrapper.getAttribute("data-custom-emoji-id") || "",
      fallback: fallback?.textContent || "",
    };
    if (
      !fallback ||
      fallback.tagName !== "SPAN" ||
      !fallback.classList.contains("rt-custom-emoji-fallback") ||
      wrapper.childElementCount !== 1 ||
      fallback.childElementCount !== 0 ||
      !isCustomEmoji(emoji)
    )
      continue;

    const fallbackElement = fallback as HTMLElement;
    // Keep the fallback in inline flow: grid items add line breaks to native copying.
    wrapper.style.display = "inline-block";
    wrapper.style.position = "relative";
    wrapper.style.width = wrapper.style.height = "1.2em";
    wrapper.style.lineHeight = "1.2em";
    wrapper.style.verticalAlign = "-0.2em";
    wrapper.style.textAlign = "center";
    // The Unicode text stays selectable and exposed to assistive technology.
    const image = element.ownerDocument.createElement("img");
    image.alt = "";
    image.setAttribute("aria-hidden", "true");
    image.draggable = false;
    image.decoding = "async";
    image.hidden = true;
    image.style.display = "none";
    image.style.position = "absolute";
    image.style.inset = "0";
    image.style.width = image.style.height = "100%";
    image.style.objectFit = "contain";
    wrapper.append(image);

    let destroyed = false;
    let observer: IntersectionObserver | null = null;
    const media = new CustomEmojiMedia(loadMedia, {
      clear: () => {
        image.onload = image.onerror = null;
        image.hidden = true;
        image.style.display = "none";
        image.removeAttribute("src");
        fallbackElement.style.opacity = "";
      },
      show: (url) => {
        image.onload = () => {
          if (destroyed || image.getAttribute("src") !== url) return;
          image.hidden = false;
          image.style.display = "inline";
          fallbackElement.style.opacity = "0";
        };
        image.onerror = () => media.clear();
        image.src = url;
      },
    });
    if (typeof IntersectionObserver === "undefined") {
      void media.load(emoji.id);
    } else {
      observer = new IntersectionObserver(
        (entries) => {
          if (destroyed || !entries.some((entry) => entry.isIntersecting)) return;
          observer?.disconnect();
          observer = null;
          void media.load(emoji.id);
        },
        { rootMargin: "100px" }
      );
      observer.observe(wrapper);
    }
    cleanups.push(() => {
      destroyed = true;
      observer?.disconnect();
      observer = null;
      media.destroy();
      image.remove();
    });
  }
  return () => cleanups.forEach((cleanup) => cleanup());
}

/** Recreate media on body/loader changes; attachment cleanup also handles unmount. */
export function customEmojiPreviews(
  html: string,
  loadMedia?: CustomEmojiMediaLoader
): Attachment<HTMLElement> {
  return (element) => {
    if (!loadMedia || !html.includes('data-custom-emoji-id="')) return;
    return mountCustomEmojiPreviews(element, loadMedia);
  };
}
