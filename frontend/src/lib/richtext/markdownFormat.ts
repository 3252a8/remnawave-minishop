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
        nodes.push(...textNode(token.text, marks));
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
      case "html":
        nodes.push(...textNode(token.text, marks));
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

function tableText(cell: Tokens.TableCell): string {
  return inlineNodes(cell.tokens)
    .map((node) => node.text || "")
    .join("");
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
        nodes.push({ type: "codeBlock", content: textNode(token.text, []) });
        break;
      case "blockquote":
        nodes.push({ type: "blockquote", content: blockNodes(token.tokens ?? []) });
        break;
      case "list": {
        const list = token as Tokens.List;
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
      case "table": {
        const table = token as Tokens.Table;
        nodes.push(
          paragraph(
            textNode(
              [
                table.header.map(tableText).join(" | "),
                ...table.rows.map((row: Tokens.TableCell[]) => row.map(tableText).join(" | ")),
              ].join("\n"),
              []
            )
          )
        );
        break;
      }
      case "hr":
        nodes.push(paragraph(textNode("—", [])));
        break;
      case "html":
        nodes.push(paragraph(textNode(token.text, [])));
        break;
      case "text":
        nodes.push(paragraph(inlineNodes(token.tokens?.length ? token.tokens : [token])));
        break;
    }
  }
  return nodes;
}

function escapeMarkdown(value: string): string {
  // Underscores embedded in a word are plain text in CommonMark. Escaping
  // them would produce noisy source such as PRIVACY\_POLICY\_URL after an
  // otherwise lossless visual-editor round trip.
  return value.replace(/([\\`*{}[\]<>()#+.!|~-])/g, "\\$1");
}

function markdownForMarks(text: string, marks: Mark[] | undefined): string {
  let result = escapeMarkdown(text);
  if (!marks) return result;
  const link = marks.find((mark) => mark.type === "link");
  for (const mark of marks) {
    if (mark.type === "bold") result = `**${result}**`;
    if (mark.type === "italic") result = `*${result}*`;
    if (mark.type === "strike") result = `~~${result}~~`;
    if (mark.type === "code") result = `\`${result.replace(/`/g, "\\`")}\``;
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
      if (node.type === "shortcode") return `{${String(node.attrs?.name || "")}}`;
      return markdownForMarks(String(node.text || ""), node.marks);
    })
    .join("");
}

function blockMarkdown(block: EditorNode): string {
  if (block.type === "heading") {
    const level = Math.max(1, Math.min(6, Number(block.attrs?.level) || 1));
    return `${"#".repeat(level)} ${inlineMarkdown(block.content)}`;
  }
  if (block.type === "codeBlock") {
    const code = (block.content || []).map((node) => node.text || "").join("");
    return `\`\`\`\n${code}\n\`\`\``;
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
      const continuation = blocks.slice(1).map((block) => {
        const value = blockMarkdown(block);
        if (block.type === "bulletList" || block.type === "orderedList") {
          return listMarkdown(block, `${indent}  `);
        }
        return value
          .split("\n")
          .map((line) => `${indent}  ${line}`)
          .join("\n");
      });
      return `${indent}${prefix}${first}${continuation.length ? `\n${continuation.join("\n")}` : ""}`;
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
  enabledMarks: ["bold", "italic", "strike", "code"],
};
