/** Visual state never removes the Unicode text used by clipboard and screen readers. */
export function setCustomEmojiPlaceholder(
  element: HTMLElement,
  fallback: HTMLElement,
  state: "loading" | "ready" | "fallback"
): void {
  const loading = state === "loading";
  fallback.style.opacity = state === "fallback" ? "" : "0";
  element.toggleAttribute("data-emoji-loading", loading);
  element.setAttribute("aria-busy", String(loading));
  element.style.background = loading
    ? "color-mix(in srgb, var(--text, #808080) 12%, transparent)"
    : "";
  element.style.borderRadius = loading ? "0.25em" : "";
}
