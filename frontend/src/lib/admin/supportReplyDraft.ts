import type { AdminSupportReplyButton } from "../../admin/sections/extensionTypes";
import { normalizeMessageButtonLink } from "./messageButtonTargets";
import { MAX_BROADCAST_BUTTONS, type BroadcastButtonDraft } from "./stores/broadcastStore.svelte";

/** Complete drafts must fit; older text-only callers retain their truncation behavior. */
export function supportReplyTextForInsertion(
  text: string,
  maxLength: number,
  allowTruncation = false
): string | null {
  const characters = Array.from(text);
  if (characters.length > maxLength && !allowTruncation) return null;
  return characters.slice(0, maxLength).join("");
}

/** Validate the complete button set before replacing any part of a reply draft. */
export function supportReplyButtonsFromDescriptors(
  buttons: readonly AdminSupportReplyButton[]
): BroadcastButtonDraft[] | null {
  if (!Array.isArray(buttons) || buttons.length > MAX_BROADCAST_BUTTONS) return null;
  const drafts: BroadcastButtonDraft[] = [];
  for (const [index, button] of buttons.entries()) {
    if (!button || typeof button.label !== "string") return null;
    if (!["url", "promo_bot", "promo_webapp", "webapp_section"].includes(button.kind)) return null;
    const url = button.kind === "url" ? normalizeMessageButtonLink(button.url) : "";
    const promoCode = typeof button.promo_code === "string" ? button.promo_code.trim() : "";
    const section = typeof button.section === "string" ? button.section.trim() : "";
    if (button.kind === "url" && !url) return null;
    if (button.kind === "webapp_section" && !section) return null;
    if (["promo_bot", "promo_webapp"].includes(button.kind) && !promoCode) return null;
    drafts.push({
      id: index + 1,
      kind: button.kind,
      label: button.label,
      url: url || "",
      promoCode,
      section,
      ...(typeof button.platform === "string" ? { platform: button.platform.trim() } : {}),
      ...(typeof button.app === "string" ? { app: button.app.trim() } : {}),
      ...(button.labels ? { labels: { ...button.labels } } : {}),
      iconCustomEmojiId: button.icon_custom_emoji_id || null,
      iconEmoji: button.icon_emoji || "",
    });
  }
  return drafts;
}
