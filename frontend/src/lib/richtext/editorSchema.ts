/**
 * Tiptap schema + toolbar command helpers for the constrained Telegram editor
 * shared by broadcasts, one-off messages and support replies. The schema is
 * deliberately limited to the Telegram∩email tag set; the atomic `shortcode`
 * node renders personalization tokens as deletable chips and serializes back to
 * `{name}` via {@link ./telegramHtml}.
 */

import { type Editor, mergeAttributes, Node } from "@tiptap/core";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";

export const ShortcodeNode = Node.create({
  name: "shortcode",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      name: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-shortcode") || "",
        renderHTML: (attributes) => ({ "data-shortcode": attributes.name }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-shortcode]" }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "rt-chip" }), `{${node.attrs.name}}`];
  },

  renderText({ node }) {
    return `{${node.attrs.name}}`;
  },
});

// Keep Markdown constructs outside the visual schema intact. They render as
// literal source and remain editable in source mode, never as executable HTML.
function markdownSourceNode(inline: boolean) {
  return Node.create({
    name: inline ? "markdownInline" : "markdownBlock",
    group: inline ? "inline" : "block",
    inline,
    atom: true,
    addAttributes() {
      return { source: { default: "", rendered: false } };
    },
    renderHTML({ node }) {
      return [inline ? "span" : "pre", { class: "rt-markdown-source" }, node.attrs.source];
    },
    renderText({ node }) {
      return String(node.attrs.source || "");
    },
  });
}

/**
 * `autolink` turns a URL into a link as it is typed. It is off for a broadcast,
 * where a template is authored around shortcodes, and on in a conversation,
 * where both sides expect to tap what the other one pasted.
 */
export function composerExtensions(
  placeholder: string,
  {
    autolink = false,
    documentBlocks = false,
  }: { autolink?: boolean; documentBlocks?: boolean } = {}
) {
  return [
    StarterKit.configure({
      heading: documentBlocks ? undefined : false,
      bulletList: documentBlocks ? undefined : false,
      orderedList: documentBlocks ? undefined : false,
      listItem: documentBlocks ? undefined : false,
      listKeymap: documentBlocks ? undefined : false,
      horizontalRule: false,
      trailingNode: false,
      link: {
        openOnClick: false,
        autolink,
        protocols: ["http", "https"],
        HTMLAttributes: { rel: "noopener nofollow", target: "_blank" },
      },
    }),
    Placeholder.configure({ placeholder }),
    ShortcodeNode,
    ...(documentBlocks ? [markdownSourceNode(true), markdownSourceNode(false)] : []),
  ];
}

/** One shortcode the composer can insert, as advertised by the backend. */
export type MessageShortcodeInfo = { name: string; cost: string; description: string };

export type ToolbarMark = "bold" | "italic" | "underline" | "strike" | "code";

export function toggleMark(editor: Editor, mark: ToolbarMark): void {
  const chain = editor.chain().focus();
  switch (mark) {
    case "bold":
      chain.toggleBold().run();
      break;
    case "italic":
      chain.toggleItalic().run();
      break;
    case "underline":
      chain.toggleUnderline().run();
      break;
    case "strike":
      chain.toggleStrike().run();
      break;
    case "code":
      chain.toggleCode().run();
      break;
  }
}

export function toggleCodeBlock(editor: Editor): void {
  editor.chain().focus().toggleCodeBlock().run();
}

export function toggleBlockquote(editor: Editor): void {
  editor.chain().focus().toggleBlockquote().run();
}

export function insertShortcode(editor: Editor, name: string): void {
  editor.chain().focus().insertContent({ type: "shortcode", attrs: { name } }).run();
}

/** Insert a ready-made link, leaving the caret outside the link mark. */
export function insertLink(editor: Editor, href: string, text: string): void {
  const trimmed = href.trim();
  if (!trimmed) return;
  editor
    .chain()
    .focus()
    .insertContent([
      { type: "text", text, marks: [{ type: "link", attrs: { href: trimmed } }] },
      { type: "text", text: " " },
    ])
    .run();
}

export function insertText(editor: Editor, text: string): void {
  editor.chain().focus().insertContent(text).run();
}

export function applyLink(editor: Editor, href: string): void {
  const trimmed = href.trim();
  const chain = editor.chain().focus();
  if (!trimmed) {
    chain.extendMarkRange("link").unsetLink().run();
    return;
  }
  if (!/^https?:\/\//i.test(trimmed)) return;
  chain.extendMarkRange("link").setLink({ href: trimmed }).run();
}

export function isMarkActive(editor: Editor, mark: string): boolean {
  return editor.isActive(mark);
}
