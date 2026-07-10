/**
 * Tiptap schema + toolbar command helpers for the constrained Telegram broadcast
 * editor. The schema is deliberately limited to the Telegram∩email tag set; the
 * atomic `shortcode` node renders personalization tokens as deletable chips and
 * serializes back to `{name}` via {@link ../telegramHtml}.
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
    return [
      "span",
      mergeAttributes(HTMLAttributes, { class: "broadcast-chip" }),
      `{${node.attrs.name}}`,
    ];
  },

  renderText({ node }) {
    return `{${node.attrs.name}}`;
  },
});

export function broadcastExtensions(placeholder: string) {
  return [
    StarterKit.configure({
      heading: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      listKeymap: false,
      horizontalRule: false,
      trailingNode: false,
      link: {
        openOnClick: false,
        autolink: false,
        protocols: ["http", "https"],
        HTMLAttributes: { rel: "noopener nofollow", target: "_blank" },
      },
    }),
    Placeholder.configure({ placeholder }),
    ShortcodeNode,
  ];
}

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
