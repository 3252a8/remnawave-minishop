/**
 * Pure serializers between the broadcast editor's ProseMirror document and the
 * Telegram-HTML wire string that the backend broadcast contract expects.
 *
 * No editor imports live here so the module is unit-testable in the plain Node
 * Vitest environment. The document shape matches what Tiptap `getJSON()` emits
 * and what `setContent()` accepts.
 *
 * Newline mapping (round-trip stable): a paragraph boundary is `\n\n` (a blank
 * line) and a hard break is a single `\n` — mirroring how Telegram renders
 * literal newlines. Unknown tags on parse become escaped literal text and are
 * reported via {@link parseTelegramHtml} so the editor can warn.
 */

export type MarkType = "bold" | "italic" | "underline" | "strike" | "code" | "link";

export type Mark = { type: MarkType; attrs?: { href?: string } };

export type InlineNode =
  | { type: "text"; text: string; marks?: Mark[] }
  | { type: "hardBreak" }
  | { type: "shortcode"; attrs: { name: string } };

export type ParagraphNode = { type: "paragraph"; content?: InlineNode[] };
export type CodeBlockNode = { type: "codeBlock"; content?: { type: "text"; text: string }[] };
export type BlockquoteNode = { type: "blockquote"; content: ParagraphNode[] };
export type BlockNode = ParagraphNode | CodeBlockNode | BlockquoteNode;
export type Doc = { type: "doc"; content: BlockNode[] };

export const SHORTCODE_TOKEN_RE = /\{([a-z_][a-z0-9_]*)\}/g;

// Marks are wrapped in this fixed order (first = innermost) so serialization is
// deterministic and idempotent regardless of how the editor nested them.
const MARK_ORDER: MarkType[] = ["code", "strike", "underline", "italic", "bold", "link"];
const MARK_TAGS: Record<MarkType, string> = {
  bold: "b",
  italic: "i",
  underline: "u",
  strike: "s",
  code: "code",
  link: "a",
};

const INLINE_TAG_TO_MARK: Record<string, MarkType> = {
  b: "bold",
  strong: "bold",
  i: "italic",
  em: "italic",
  u: "underline",
  ins: "underline",
  s: "strike",
  strike: "strike",
  del: "strike",
  code: "code",
  a: "link",
};

export function escapeHtml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function unescapeHtml(value: string): string {
  return value
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&");
}

function marksKey(marks: Mark[] | undefined): string {
  if (!marks || !marks.length) return "";
  return marks
    .map((m) => (m.type === "link" ? `link:${m.attrs?.href || ""}` : m.type))
    .sort()
    .join("|");
}

function wrapMarks(text: string, marks: Mark[] | undefined): string {
  if (!marks || !marks.length) return text;
  let html = text;
  for (const type of MARK_ORDER) {
    const mark = marks.find((m) => m.type === type);
    if (!mark) continue;
    if (type === "link") {
      const href = String(mark.attrs?.href || "").trim();
      html = `<a href="${escapeHtml(href).replace(/"/g, "&quot;")}">${html}</a>`;
    } else {
      const tag = MARK_TAGS[type];
      html = `<${tag}>${html}</${tag}>`;
    }
  }
  return html;
}

function serializeInline(nodes: InlineNode[] | undefined): string {
  if (!nodes) return "";
  const parts: string[] = [];
  for (const node of nodes) {
    if (node.type === "hardBreak") {
      parts.push("\n");
    } else if (node.type === "shortcode") {
      parts.push(`{${node.attrs.name}}`);
    } else if (node.type === "text") {
      parts.push(wrapMarks(escapeHtml(node.text), node.marks));
    }
  }
  return parts.join("");
}

function serializeBlock(block: BlockNode): string {
  if (block.type === "codeBlock") {
    const text = (block.content || []).map((n) => n.text).join("");
    return `<pre>${escapeHtml(text)}</pre>`;
  }
  if (block.type === "blockquote") {
    const inner = (block.content || []).map((p) => serializeInline(p.content)).join("\n");
    return `<blockquote>${inner}</blockquote>`;
  }
  return serializeInline(block.content);
}

export function docToTelegramHtml(doc: Doc | null | undefined): string {
  if (!doc || !doc.content) return "";
  return doc.content
    .map(serializeBlock)
    .filter((block, index, all) => block !== "" || all.length === 1)
    .join("\n\n");
}

type Token =
  | { kind: "text"; value: string }
  | { kind: "open"; name: string; attrs: string; raw: string }
  | { kind: "close"; name: string; raw: string };

const TAG_RE = /<(\/?)([a-zA-Z][\w-]*)((?:\s+[^<>]*?)?)\/?>/g;

function tokenize(html: string): Token[] {
  const tokens: Token[] = [];
  let cursor = 0;
  let match: RegExpExecArray | null;
  TAG_RE.lastIndex = 0;
  while ((match = TAG_RE.exec(html)) !== null) {
    if (match.index > cursor) {
      tokens.push({ kind: "text", value: html.slice(cursor, match.index) });
    }
    const name = match[2].toLowerCase();
    if (match[1]) {
      tokens.push({ kind: "close", name, raw: match[0] });
    } else {
      tokens.push({ kind: "open", name, attrs: match[3] || "", raw: match[0] });
    }
    cursor = match.index + match[0].length;
  }
  if (cursor < html.length) tokens.push({ kind: "text", value: html.slice(cursor) });
  return tokens;
}

function hrefFromAttrs(attrs: string): string {
  const match = attrs.match(/href\s*=\s*("([^"]*)"|'([^']*)'|([^\s"'>]+))/i);
  if (!match) return "";
  return unescapeHtml(match[2] ?? match[3] ?? match[4] ?? "");
}

function mergeAdjacentText(nodes: InlineNode[]): InlineNode[] {
  const out: InlineNode[] = [];
  for (const node of nodes) {
    const prev = out[out.length - 1];
    if (
      node.type === "text" &&
      prev &&
      prev.type === "text" &&
      marksKey(prev.marks) === marksKey(node.marks)
    ) {
      prev.text += node.text;
    } else {
      out.push(node);
    }
  }
  return out;
}

function toParagraphs(nodes: InlineNode[]): ParagraphNode[] {
  const paragraphs: ParagraphNode[] = [];
  let current: InlineNode[] = [];
  let i = 0;
  while (i < nodes.length) {
    const node = nodes[i];
    if (node.type === "hardBreak") {
      let run = 0;
      while (i < nodes.length && nodes[i].type === "hardBreak") {
        run += 1;
        i += 1;
      }
      if (run >= 2) {
        paragraphs.push({ type: "paragraph", content: mergeAdjacentText(current) });
        current = [];
      } else {
        current.push(node);
      }
      continue;
    }
    current.push(node);
    i += 1;
  }
  paragraphs.push({ type: "paragraph", content: mergeAdjacentText(current) });
  return paragraphs.filter((p) => (p.content || []).length > 0);
}

export type ParsedTelegramHtml = { doc: Doc; unknownTags: string[] };

export function parseTelegramHtml(html: string): ParsedTelegramHtml {
  const tokens = tokenize(html || "");
  const blocks: BlockNode[] = [];
  const unknownTags = new Set<string>();
  const markStack: Mark[] = [];

  let mode: "inline" | "pre" | "blockquote" = "inline";
  let inlineBuf: InlineNode[] = [];
  let quoteBuf: InlineNode[] = [];
  let preText = "";

  const target = (): InlineNode[] => (mode === "blockquote" ? quoteBuf : inlineBuf);

  const addText = (raw: string): void => {
    const marks = markStack.length ? markStack.map((m) => ({ ...m })) : undefined;
    const buf = target();
    const segments = raw.split("\n");
    segments.forEach((segment, index) => {
      if (index > 0) buf.push({ type: "hardBreak" });
      let last = 0;
      SHORTCODE_TOKEN_RE.lastIndex = 0;
      let sc: RegExpExecArray | null;
      while ((sc = SHORTCODE_TOKEN_RE.exec(segment)) !== null) {
        if (sc.index > last) buf.push({ type: "text", text: segment.slice(last, sc.index), marks });
        buf.push({ type: "shortcode", attrs: { name: sc[1] } });
        last = sc.index + sc[0].length;
      }
      if (last < segment.length) buf.push({ type: "text", text: segment.slice(last), marks });
    });
  };

  const flushInline = (): void => {
    for (const paragraph of toParagraphs(inlineBuf)) blocks.push(paragraph);
    inlineBuf = [];
  };

  for (const token of tokens) {
    if (token.kind === "text") {
      const value = unescapeHtml(token.value);
      if (mode === "pre") preText += value;
      else addText(value);
      continue;
    }

    if (token.kind === "open") {
      if (token.name === "pre" && mode === "inline") {
        flushInline();
        mode = "pre";
        preText = "";
        continue;
      }
      if (token.name === "blockquote" && mode === "inline") {
        flushInline();
        mode = "blockquote";
        quoteBuf = [];
        continue;
      }
      const markType = INLINE_TAG_TO_MARK[token.name];
      if (markType && mode !== "pre") {
        markStack.push(
          markType === "link"
            ? { type: "link", attrs: { href: hrefFromAttrs(token.attrs) } }
            : { type: markType }
        );
        continue;
      }
      if (mode !== "pre") {
        unknownTags.add(token.name);
        addText(token.raw);
      }
      continue;
    }

    // close tag
    if (token.name === "pre" && mode === "pre") {
      blocks.push({
        type: "codeBlock",
        content: preText ? [{ type: "text", text: preText }] : [],
      });
      mode = "inline";
      continue;
    }
    if (token.name === "blockquote" && mode === "blockquote") {
      const merged = mergeAdjacentText(quoteBuf);
      blocks.push({ type: "blockquote", content: [{ type: "paragraph", content: merged }] });
      quoteBuf = [];
      mode = "inline";
      continue;
    }
    const closeMark = INLINE_TAG_TO_MARK[token.name];
    if (closeMark && mode !== "pre") {
      for (let i = markStack.length - 1; i >= 0; i -= 1) {
        if (markStack[i].type === closeMark) {
          markStack.splice(i, 1);
          break;
        }
      }
      continue;
    }
    if (mode !== "pre") {
      unknownTags.add(token.name);
      addText(token.raw);
    }
  }

  flushInline();
  if (!blocks.length) blocks.push({ type: "paragraph" });
  return { doc: { type: "doc", content: blocks }, unknownTags: [...unknownTags] };
}

export function telegramHtmlToDoc(html: string): Doc {
  return parseTelegramHtml(html).doc;
}

/**
 * Render a wire string to safe display HTML for the live preview pane,
 * substituting shortcode chips with sample values. Built from the parsed
 * structure so text is always escaped — never `{@html}` of raw input.
 */
export function previewHtmlFromWire(html: string, samples: Record<string, string> = {}): string {
  const doc = telegramHtmlToDoc(html);
  const renderInline = (nodes: InlineNode[] | undefined): string => {
    if (!nodes) return "";
    return nodes
      .map((node) => {
        if (node.type === "hardBreak") return "<br>";
        if (node.type === "shortcode") {
          const value = samples[node.attrs.name] ?? `{${node.attrs.name}}`;
          return `<span class="broadcast-preview-chip">${escapeHtml(value)}</span>`;
        }
        return wrapMarks(escapeHtml(node.text), node.marks);
      })
      .join("");
  };
  return doc.content
    .map((block) => {
      if (block.type === "codeBlock") {
        const text = (block.content || []).map((n) => n.text).join("");
        return `<pre>${escapeHtml(text)}</pre>`;
      }
      if (block.type === "blockquote") {
        return `<blockquote>${(block.content || [])
          .map((p) => renderInline(p.content))
          .join("<br>")}</blockquote>`;
      }
      return `<p>${renderInline(block.content) || "<br>"}</p>`;
    })
    .join("");
}

export function unknownShortcodeTokens(html: string, known: Iterable<string>): string[] {
  const knownSet = new Set(known);
  const found = new Set<string>();
  SHORTCODE_TOKEN_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = SHORTCODE_TOKEN_RE.exec(html || "")) !== null) {
    if (!knownSet.has(match[1])) found.add(match[1]);
  }
  return [...found];
}
