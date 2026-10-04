/** Vocabulary shared by every host of {@link RichTextEditor}. */

import type { Doc } from "./telegramHtml.js";
import type { ToolbarMark } from "./editorSchema.js";

/** Hosts supply authenticated media; generic editor code knows only the entity ID. */
export type CustomEmojiMediaLoader = (id: string, signal: AbortSignal) => Promise<Blob>;

/**
 * Storage adapter for a shared rich-text surface.
 *
 * Broadcasts use Telegram HTML, while information pages are persisted as
 * Markdown. Keeping this conversion at the editor boundary lets both hosts
 * share the accessible toolbar and source-mode UX without changing either
 * wire format.
 */
export type RichTextFormat = {
  fromSource: (value: string) => Doc;
  toSource: (document: Doc) => string;
  /** Raw source has its own syntax, so hosts can hide HTML-only toolbar actions. */
  sourceModeControls?: boolean;
  /** Omit marks with no safe source-format equivalent (for example underline in Markdown). */
  enabledMarks?: ToolbarMark[];
  /** The storage format can retain Telegram custom emoji entities. */
  customEmoji?: boolean;
};

/**
 * Every string the editor puts on screen.
 *
 * The editor takes finished captions rather than a translate function on
 * purpose: it is mounted from the admin panel (`admin_*` keys) and from the
 * customer Mini App (`wa_*` keys), and the locale-scope gate holds each host
 * to its own prefix.
 */
export type RichTextLabels = {
  toolbar: string;
  bold: string;
  italic: string;
  underline: string;
  strike: string;
  code: string;
  pre: string;
  quote: string;
  link: string;
  linkApply: string;
  linkPlaceholder: string;
  /** Caption of the source-mode toggle while the editor is showing markup. */
  sourceOn: string;
  /** …and while it is showing the source. */
  sourceOff: string;
  insert: string;
  insertEmpty: string;
  shortcodes: string;
  shortcodesLoading: string;
  shortcodePanelBadge: string;
  customEmoji: string;
  customEmojiSourceUnavailable: string;
  customEmojiCodeFallback: string;
  customEmojiInvalid: string;
  customEmojiUnavailable: string;
};

/** One entry of the host-supplied "insert" menu. */
export type RichTextQuickInsert = {
  id: string;
  label: string;
  description?: string;
  /** Shown as a small badge, e.g. to mark a link the customer sees. */
  badge?: string;
  /** Nothing to insert yet (a link that has not loaded); shown but inert. */
  disabled?: boolean;
  content:
    | { kind: "link"; href: string; text: string }
    | { kind: "text"; text: string }
    /** A curated shortcut into the shortcode vocabulary the host already has. */
    | { kind: "shortcode"; name: string };
};
