/** Visual state never removes the Unicode text used by clipboard and screen readers. */
export function setCustomEmojiPlaceholder(
  element: HTMLElement,
  fallback: HTMLElement,
  state: "loading" | "ready" | "fallback"
): void {
  const loading = state === "loading";
  fallback.style.opacity = state === "fallback" ? "" : "0";
  element.classList.toggle("ui-skeleton", loading);
  element.toggleAttribute("data-emoji-loading", loading);
  element.setAttribute("aria-busy", String(loading));
  element.style.borderRadius = loading ? "0.25em" : "";
}
