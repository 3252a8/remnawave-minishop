import { describe, expect, it } from "vitest";

import {
  type Doc,
  docToTelegramHtml,
  parseTelegramHtml,
  previewHtmlFromWire,
  telegramHtmlToDoc,
  unknownShortcodeTokens,
} from "./telegramHtml";

const roundtrip = (html: string): string => docToTelegramHtml(telegramHtmlToDoc(html));

describe("docToTelegramHtml", () => {
  it("serializes marks, shortcodes and newlines", () => {
    const doc: Doc = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "Hi " },
            { type: "shortcode", attrs: { name: "first_name" } },
            { type: "text", text: "!" },
            { type: "hardBreak" },
            { type: "text", text: "bold", marks: [{ type: "bold" }] },
          ],
        },
      ],
    };
    expect(docToTelegramHtml(doc)).toBe("Hi {first_name}!\n<b>bold</b>");
  });

  it("escapes text but not shortcodes", () => {
    const doc: Doc = {
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "a < b & c" }] }],
    };
    expect(docToTelegramHtml(doc)).toBe("a &lt; b &amp; c");
  });

  it("serializes code blocks and blockquotes", () => {
    const doc: Doc = {
      type: "doc",
      content: [
        { type: "codeBlock", content: [{ type: "text", text: "x{a}" }] },
        {
          type: "blockquote",
          content: [{ type: "paragraph", content: [{ type: "text", text: "q" }] }],
        },
      ],
    };
    expect(docToTelegramHtml(doc)).toBe("<pre>x{a}</pre>\n\n<blockquote>q</blockquote>");
  });
});

describe("parseTelegramHtml", () => {
  it("extracts shortcodes and marks", () => {
    const { doc } = parseTelegramHtml("Hi <b>{first_name}</b>");
    expect(doc.content[0]).toEqual({
      type: "paragraph",
      content: [
        { type: "text", text: "Hi " },
        { type: "shortcode", attrs: { name: "first_name" } },
      ],
    });
  });

  it("keeps http links and reports unknown tags as text", () => {
    const link = roundtrip('<a href="https://e.com">L</a>');
    expect(link).toBe('<a href="https://e.com">L</a>');
    const parsed = parseTelegramHtml("<p>hi</p>");
    expect(parsed.unknownTags).toContain("p");
    expect(docToTelegramHtml(parsed.doc)).toContain("&lt;p&gt;hi&lt;/p&gt;");
  });

  it("splits paragraphs on blank lines and keeps single breaks", () => {
    const { doc } = parseTelegramHtml("a\nb\n\nc");
    expect(doc.content).toHaveLength(2);
    expect(doc.content[0]).toEqual({
      type: "paragraph",
      content: [{ type: "text", text: "a" }, { type: "hardBreak" }, { type: "text", text: "b" }],
    });
  });
});

describe("round-trip stability", () => {
  const cases = [
    "plain text",
    "Hi {first_name}, welcome!",
    "<b>bold</b> and <i>italic</i> and <u>u</u> and <s>s</s>",
    "<b>outer <i>inner</i> end</b>",
    "<code>literal {brace}</code>",
    '<a href="https://t.me/x">link</a>',
    "line one\nline two\n\nnew paragraph",
    "<pre>code\nblock</pre>\n\nafter",
    "<blockquote>quoted {days_left}</blockquote>",
  ];
  for (const input of cases) {
    it(`is idempotent for: ${input.slice(0, 24)}`, () => {
      const once = roundtrip(input);
      expect(roundtrip(once)).toBe(once);
    });
  }
});

describe("previewHtmlFromWire", () => {
  it("substitutes samples and stays XSS-safe", () => {
    const html = previewHtmlFromWire("Hi {first_name} <b>x</b>", { first_name: "<script>" });
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("<b>x</b>");
    expect(html).not.toContain("<script>");
  });

  it("escapes raw angle brackets from source-mode input", () => {
    const html = previewHtmlFromWire("<img src=x onerror=alert(1)>");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});

describe("unknownShortcodeTokens", () => {
  it("reports tokens not in the known set", () => {
    expect(unknownShortcodeTokens("{first_name} {frist_name}", ["first_name"])).toEqual([
      "frist_name",
    ]);
  });
});
