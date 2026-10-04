import type { RichTextLabels } from "$lib/richtext/types";

type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

/**
 * Customer captions for the shared rich-text editor.
 *
 * The customer gets the formatting half of the editor and none of the staff
 * half: there is no raw-markup toggle, no personalization tokens and no insert
 * menu, so those captions are never read and are filled with empty strings
 * rather than inventing locale keys nobody displays.
 */
export function webappRichTextLabels(t: TranslateFn): RichTextLabels {
  return {
    toolbar: t("wa_format_toolbar"),
    bold: t("wa_format_bold"),
    italic: t("wa_format_italic"),
    underline: t("wa_format_underline"),
    strike: t("wa_format_strike"),
    code: t("wa_format_code"),
    pre: t("wa_format_pre"),
    quote: t("wa_format_quote"),
    link: t("wa_format_link"),
    linkApply: t("wa_format_link_apply"),
    linkPlaceholder: "https://...",
    sourceOn: "",
    sourceOff: "",
    insert: "",
    insertEmpty: "",
    shortcodes: "",
    shortcodesLoading: "",
    shortcodePanelBadge: "",
    customEmoji: "",
    customEmojiSourceUnavailable: "",
    customEmojiCodeFallback: "",
    customEmojiInvalid: t("wa_format_custom_emoji_invalid"),
    customEmojiUnavailable: "",
  };
}
