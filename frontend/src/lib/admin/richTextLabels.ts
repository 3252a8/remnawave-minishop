import type { RichTextLabels } from "$lib/richtext/types";

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

/**
 * Admin captions for the shared rich-text editor.
 *
 * The editor takes finished strings, so the `admin_`-prefixed keys stay in one
 * place instead of being restated by every panel that mounts it.
 */
export function adminRichTextLabels(at: TranslateFn, overrides: Partial<RichTextLabels> = {}) {
  return {
    toolbar: at("broadcast_toolbar", {}, "Formatting"),
    bold: at("broadcast_format_bold", {}, "Bold"),
    italic: at("broadcast_format_italic", {}, "Italic"),
    underline: at("broadcast_format_underline", {}, "Underline"),
    strike: at("broadcast_format_strike", {}, "Strikethrough"),
    code: at("broadcast_format_code", {}, "Monospace"),
    pre: at("broadcast_format_pre", {}, "Code block"),
    quote: at("broadcast_format_quote", {}, "Quote"),
    link: at("broadcast_format_link", {}, "Link"),
    linkApply: at("broadcast_link_apply", {}, "OK"),
    linkPlaceholder: "https://...",
    sourceOn: at("broadcast_source_mode_on", {}, "HTML"),
    sourceOff: at("broadcast_source_mode_off", {}, "Editor"),
    insert: at("support_insert_menu", {}, "Insert"),
    insertEmpty: at("support_insert_empty", {}, "Nothing to insert yet"),
    shortcodes: at("broadcast_insert_shortcode", {}, "{ } Shortcode"),
    shortcodesLoading: at("broadcast_shortcodes_loading", {}, "Loading..."),
    shortcodePanelBadge: at("broadcast_shortcode_panel_badge", {}, "panel"),
    customEmoji: at("richtext_custom_emoji", {}, "Emoji"),
    customEmojiSourceUnavailable: at(
      "richtext_custom_emoji_source",
      {},
      "Switch to the editor to insert an emoji."
    ),
    customEmojiCodeFallback: at(
      "richtext_custom_emoji_code",
      {},
      "Insert the Unicode fallback in code."
    ),
    customEmojiInvalid: at(
      "richtext_custom_emoji_invalid",
      {},
      "Invalid custom emoji markup is shown as text. Check the ID and emoji fallback."
    ),
    customEmojiUnavailable: at(
      "richtext_custom_emoji_unavailable",
      {},
      "The emoji picker could not be opened. Try again."
    ),
    ...overrides,
  } satisfies RichTextLabels;
}
