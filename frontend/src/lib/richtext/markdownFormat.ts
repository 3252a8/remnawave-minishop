import { marked, type Token, type Tokens } from "marked";

import type { Doc, Mark } from "./telegramHtml.js";
import type { RichTextFormat } from "./types.js";

type EditorNode = {
  type: string;
  attrs?: Record<string, unknown>;
  content?: EditorNode[];
  marks?: Mark[];
  text?: string;
};

function cloneMarks(marks: Mark[]): Mark[] | undefined {
  return marks.length
    ? marks.map((mark) => ({ ...mark, attrs: mark.attrs && { ...mark.attrs } }))
    : undefined;
}

function textNode(text: string, marks: Mark[]): EditorNode[] {
  if (!text) return [];
  return [{ type: "text", text, marks: cloneMarks(marks) }];
}

function sourceNode(token: Token, inline = false, marks: Mark[] = []): EditorNode {
  return {
    type: inline ? "markdownInline" : "markdownBlock",
    attrs: { source: inline ? token.raw : token.raw.trimEnd() },
    marks: cloneMarks(marks),
  };
}

function inlineNodes(tokens: Token[], marks: Mark[] = []): EditorNode[] {
  const nodes: EditorNode[] = [];
  for (const token of tokens) {
    switch (token.type) {
      case "strong":
        nodes.push(...inlineNodes(token.tokens ?? [], [...marks, { type: "bold" }]));
        break;
      case "em":
        nodes.push(...inlineNodes(token.tokens ?? [], [...marks, { type: "italic" }]));
        break;
      case "del":
        nodes.push(...inlineNodes(token.tokens ?? [], [...marks, { type: "strike" }]));
        break;
      case "codespan":
        nodes.push(...textNode(token.text, [...marks, { type: "code" }]));
        break;
      case "link":
        if (token.title) {
          nodes.push(sourceNode(token, true, marks));
          break;
        }
        nodes.push(
          ...inlineNodes(token.tokens ?? [], [
            ...marks,
            { type: "link", attrs: { href: String(token.href || "") } },
          ])
        );
        break;
      case "br":
        nodes.push({ type: "hardBreak" });
        break;
      case "image":
        nodes.push(sourceNode(token, true, marks));
        break;
      case "checkbox":
        nodes.push(...textNode(token.checked ? "[x] " : "[ ] ", marks));
        break;
      case "text":
        if (token.tokens?.length) {
          nodes.push(...inlineNodes(token.tokens, marks));
        } else {
          nodes.push(...textNode(token.text, marks));
        }
        break;
      case "escape":
        nodes.push(...textNode(token.text, marks));
        break;
      case "html":
        nodes.push(sourceNode(token, true, marks));
        break;
      default:
        if ("text" in token && typeof token.text === "string") {
          nodes.push(...textNode(token.text, marks));
        }
    }
  }
  return nodes;
}

function paragraph(content: EditorNode[]): EditorNode {
  return { type: "paragraph", content };
}

function blockNodes(tokens: Token[]): EditorNode[] {
  const nodes: EditorNode[] = [];
  for (const token of tokens) {
    switch (token.type) {
      case "heading":
        nodes.push({
          type: "heading",
          attrs: { level: token.depth },
          content: inlineNodes(token.tokens ?? []),
        });
        break;
      case "paragraph":
        nodes.push(paragraph(inlineNodes(token.tokens ?? [])));
        break;
      case "code":
        nodes.push(
          token.lang ? sourceNode(token) : { type: "codeBlock", content: textNode(token.text, []) }
        );
        break;
      case "blockquote":
        nodes.push({ type: "blockquote", content: blockNodes(token.tokens ?? []) });
        break;
      case "list": {
        const list = token as Tokens.List;
        if (list.items.some((item) => item.task)) {
          nodes.push(sourceNode(token));
          break;
        }
        nodes.push({
          type: list.ordered ? "orderedList" : "bulletList",
          attrs: list.ordered && typeof list.start === "number" ? { start: list.start } : undefined,
          content: list.items.map((item: Tokens.ListItem) => ({
            type: "listItem",
            content: blockNodes(item.tokens),
          })),
        });
        break;
      }
      case "table":
      case "def":
      case "hr":
      case "html":
        nodes.push(sourceNode(token));
        break;
      case "text":
        nodes.push(paragraph(inlineNodes(token.tokens?.length ? token.tokens : [token])));
        break;
    }
  }
  return nodes;
}

function escapeMarkdown(value: string): string {
  return value
    .replace(/([\\`*{}[\]<>()#+.!|~-])/g, "\\$1")
    .replace(/(?<![\p{L}\p{N}])_|_(?![\p{L}\p{N}])/gu, "\\_");
}

function markdownForMarks(text: string, marks: Mark[] | undefined, raw = false): string {
  let result = raw ? text : escapeMarkdown(text);
  if (!marks) return result;
  if (marks.some((mark) => mark.type === "code")) {
    const runs = text.match(/`+/g) || [];
    const fence = "`".repeat(Math.max(0, ...runs.map((run) => run.length)) + 1);
    const pad = /^`|`$|^ .* $/.test(text) && /[^ ]/.test(text) ? " " : "";
    result = `${fence}${pad}${text}${pad}${fence}`;
  }
  const link = marks.find((mark) => mark.type === "link");
  for (const mark of marks) {
    if (mark.type === "bold") result = `**${result}**`;
    if (mark.type === "italic") result = `*${result}*`;
    if (mark.type === "strike") result = `~~${result}~~`;
  }
  if (link) {
    const href = String(link.attrs?.href || "").trim();
    if (href) result = `[${result}](${href.replace(/[()\\]/g, "\\$&")})`;
  }
  return result;
}

function inlineMarkdown(nodes: EditorNode[] | undefined): string {
  if (!nodes) return "";
  return nodes
    .map((node) => {
      if (node.type === "hardBreak") return "  \n";
      if (node.type === "markdownInline")
        return markdownForMarks(String(node.attrs?.source || ""), node.marks, true);
      if (node.type === "shortcode") return `{${String(node.attrs?.name || "")}}`;
      if (node.type === "customEmoji")
        return markdownForMarks(String(node.attrs?.fallback || ""), node.marks);
      return markdownForMarks(String(node.text || ""), node.marks);
    })
    .join("");
}

function blockMarkdown(block: EditorNode): string {
  if (block.type === "markdownBlock") return String(block.attrs?.source || "");
  if (block.type === "heading") {
    const level = Math.max(1, Math.min(6, Number(block.attrs?.level) || 1));
    return `${"#".repeat(level)} ${inlineMarkdown(block.content)}`;
  }
  if (block.type === "codeBlock") {
    const code = (block.content || []).map((node) => node.text || "").join("");
    const runs = code.match(/`+/g) || [];
    const fence = "`".repeat(Math.max(2, ...runs.map((run) => run.length)) + 1);
    return `${fence}\n${code}\n${fence}`;
  }
  if (block.type === "blockquote") {
    return (block.content || [])
      .map(blockMarkdown)
      .join("\n\n")
      .split("\n")
      .map((line) => (line ? `> ${line}` : ">"))
      .join("\n");
  }
  if (block.type === "bulletList" || block.type === "orderedList") return listMarkdown(block);
  return inlineMarkdown(block.content);
}

function listMarkdown(list: EditorNode, indent = ""): string {
  const ordered = list.type === "orderedList";
  const start = Number(list.attrs?.start) || 1;
  return (list.content || [])
    .map((item, index) => {
      const blocks = item.content || [];
      const first = blocks[0] ? blockMarkdown(blocks[0]) : "";
      const prefix = ordered ? `${start + index}. ` : "- ";
      const childIndent = `${indent}${" ".repeat(prefix.length)}`;
      const continuation = blocks.slice(1).map((block) => {
        const value = blockMarkdown(block);
        if (block.type === "bulletList" || block.type === "orderedList") {
          return listMarkdown(block, childIndent);
        }
        return value
          .split("\n")
          .map((line) => `${childIndent}${line}`)
          .join("\n");
      });
      const firstIndented = first.replace(/\n/g, `\n${childIndent}`);
      return `${indent}${prefix}${firstIndented}${continuation.length ? `\n${continuation.join("\n")}` : ""}`;
    })
    .join("\n");
}

function editorDocToMarkdown(document: Doc): string {
  return ((document.content || []) as unknown as EditorNode[])
    .map(blockMarkdown)
    .filter((block) => block || document.content.length === 1)
    .join("\n\n")
    .trim();
}

function markdownDocument(value: string): Doc {
  const content = blockNodes(marked.lexer(value, { gfm: true }));
  // Tiptap's Placeholder extension only decorates an actual empty textblock.
  // A bare doc is valid JSON, but has nowhere to render the placeholder until
  // the first transaction inserts a paragraph.
  return {
    type: "doc",
    content: content.length ? content : [paragraph([])],
  } as unknown as Doc;
}

/**
 * Markdown-backed information pages share the broadcast editor's toolbar and
 * accessibility behavior, but their source mode and persisted value remain
 * Markdown. Heading and list nodes are enabled only for this format.
 */
export const markdownFormat: RichTextFormat = {
  fromSource: markdownDocument,
  toSource: editorDocToMarkdown,
  sourceModeControls: false,
  customEmoji: false,
  enabledMarks: ["bold", "italic", "strike", "code"],
};
