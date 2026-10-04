/**
 * Tiptap schema + toolbar command helpers for the constrained Telegram editor
 * shared by broadcasts, one-off messages and support replies. The schema
 * retains Telegram custom emoji while display/email adapters use their Unicode
 * fallback. Atomic nodes keep IDs and personalization tokens intact during
 * clipboard, deletion and history operations.
 */

import { type Editor, mergeAttributes, Node } from "@tiptap/core";
import Placeholder from "@tiptap/extension-placeholder";
import StarterKit from "@tiptap/starter-kit";
import { Plugin, type Transaction } from "@tiptap/pm/state";

import { isCustomEmoji, isCustomEmojiFallback, type CustomEmoji } from "./customEmoji.js";
import { createCustomEmojiNodeView } from "./customEmojiNodeView.js";
import type { CustomEmojiMediaLoader } from "./types.js";

export const CustomEmojiNode = Node.create<{ loadMedia?: CustomEmojiMediaLoader }>({
  name: "customEmoji",
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addOptions() {
    return { loadMedia: undefined };
  },

  addNodeView() {
    return this.options.loadMedia ? createCustomEmojiNodeView(this.options.loadMedia) : null;
  },

  addAttributes() {
    return {
      id: { default: "", rendered: false },
      fallback: { default: "", rendered: false },
    };
  },

  parseHTML() {
    return ["span[data-custom-emoji-id]", "tg-emoji"].map((tag) => ({
      tag,
      getAttrs: (element: HTMLElement) => {
        const attrs = {
          id:
            element.getAttribute("data-custom-emoji-id") || element.getAttribute("emoji-id") || "",
          fallback: element.textContent || "",
        };
        if (element.children.length || element.closest("pre,code") || !isCustomEmoji(attrs))
          return false;
        return attrs;
      },
    }));
  },

  renderHTML({ node }) {
    return [
      "span",
      {
        class: "rt-custom-emoji",
        "data-custom-emoji-id": String(node.attrs.id || ""),
      },
      String(node.attrs.fallback || ""),
    ];
  },

  renderText({ node }) {
    return String(node.attrs.fallback || "");
  },

  addKeyboardShortcuts() {
    return {
      "Mod-Alt-c": () => {
        toggleCodeBlock(this.editor);
        return true;
      },
    };
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        appendTransaction(transactions, _oldState, state) {
          if (!transactions.some((transaction) => transaction.docChanged)) return null;
          const tr = state.tr;
          state.doc.descendants((node, position) => {
            if (
              node.type.name !== "customEmoji" ||
              !node.marks.some((mark) => mark.type.name === "code")
            )
              return;
            tr.replaceWith(
              tr.mapping.map(position),
              tr.mapping.map(position + node.nodeSize),
              state.schema.text(String(node.attrs.fallback || ""), node.marks)
            );
          });
          return tr.docChanged ? tr : null;
        },
      }),
    ];
  },
});

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
    loadCustomEmojiMedia,
  }: {
    autolink?: boolean;
    documentBlocks?: boolean;
    loadCustomEmojiMedia?: CustomEmojiMediaLoader;
  } = {}
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
    CustomEmojiNode.configure({ loadMedia: loadCustomEmojiMedia }),
    ...(documentBlocks ? [markdownSourceNode(true), markdownSourceNode(false)] : []),
  ];
}

/** One shortcode the composer can insert, as advertised by the backend. */
export type MessageShortcodeInfo = { name: string; cost: string; description: string };

export type ToolbarMark = "bold" | "italic" | "underline" | "strike" | "code";

export function toolbarMarkButtons(
  labels: Record<ToolbarMark, string>
): { mark: ToolbarMark; label: string; icon: string }[] {
  return [
    { mark: "bold", label: labels.bold, icon: "B" },
    { mark: "italic", label: labels.italic, icon: "I" },
    { mark: "underline", label: labels.underline, icon: "U" },
    { mark: "strike", label: labels.strike, icon: "S" },
    { mark: "code", label: labels.code, icon: "</>" },
  ];
}

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
      if (!editor.isActive("code"))
        chain.command(({ tr }) => {
          replaceSelectedCustomEmoji(tr);
          return true;
        });
      chain.toggleCode().run();
      break;
  }
}

export function toggleCodeBlock(editor: Editor): void {
  const chain = editor.chain().focus();
  if (!editor.isActive("codeBlock"))
    chain.command(({ tr }) => {
      replaceSelectedCustomEmoji(tr, true);
      return true;
    });
  chain.toggleCodeBlock().run();
}

/** Code-block conversion would otherwise discard inline atoms outside the selection. */
function replaceSelectedCustomEmoji(tr: Transaction, wholeTextblocks = false): void {
  const replacements: { position: number; size: number; fallback: string }[] = [];
  tr.doc.nodesBetween(tr.selection.from, tr.selection.to, (node, position) => {
    if (wholeTextblocks && node.isTextblock) {
      node.descendants((child, offset) => {
        if (child.type.name === "customEmoji")
          replacements.push({
            position: position + 1 + offset,
            size: child.nodeSize,
            fallback: String(child.attrs.fallback || ""),
          });
      });
      return false;
    }
    if (node.type.name === "customEmoji")
      replacements.push({
        position,
        size: node.nodeSize,
        fallback: String(node.attrs.fallback || ""),
      });
  });
  for (const { position, size, fallback } of replacements.reverse()) {
    tr.replaceWith(position, position + size, fallback ? tr.doc.type.schema.text(fallback) : []);
  }
}

export function toggleBlockquote(editor: Editor): void {
  editor.chain().focus().toggleBlockquote().run();
}

export function insertShortcode(editor: Editor, name: string): void {
  editor.chain().focus().insertContent({ type: "shortcode", attrs: { name } }).run();
}

/** Both picker tabs use this boundary; ordinary emoji and code use plain text. */
export function insertCustomEmoji(editor: Editor, emoji: CustomEmoji): void {
  if (!isCustomEmojiFallback(emoji.fallback)) return;
  if (!emoji.id || editor.isActive("code") || editor.isActive("codeBlock")) {
    editor.chain().focus().insertContent({ type: "text", text: emoji.fallback }).run();
    return;
  }
  if (!isCustomEmoji(emoji)) return;
  const marks = (editor.state.storedMarks || editor.state.selection.$from.marks()).map((mark) => ({
    type: mark.type.name,
    attrs: mark.attrs,
  }));
  editor.chain().focus().insertContent({ type: "customEmoji", attrs: emoji, marks }).run();
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

export function editorActiveMarks(editor: Editor | null) {
  return {
    bold: editor?.isActive("bold") ?? false,
    italic: editor?.isActive("italic") ?? false,
    underline: editor?.isActive("underline") ?? false,
    strike: editor?.isActive("strike") ?? false,
    code: editor?.isActive("code") ?? false,
    codeBlock: editor?.isActive("codeBlock") ?? false,
    blockquote: editor?.isActive("blockquote") ?? false,
    link: editor?.isActive("link") ?? false,
  };
}
