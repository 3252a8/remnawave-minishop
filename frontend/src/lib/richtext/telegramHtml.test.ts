import { describe, expect, it } from "vitest";
import { getSchema } from "@tiptap/core";
import { EditorState, NodeSelection, TextSelection } from "@tiptap/pm/state";
import { history, redo, undo } from "@tiptap/pm/history";

import { composerExtensions } from "./editorSchema";
import { isCustomEmojiFallback, isCustomEmojiId } from "./customEmoji";

import {
  type Doc,
  docToTelegramHtml,
  parseTelegramHtml,
  messageDisplayHtml,
  previewHtmlFromWire,
  telegramHtmlToDoc,
  unknownShortcodeTokens,
  wireTextLength,
} from "./telegramHtml";

const roundtrip = (html: string): string => docToTelegramHtml(telegramHtmlToDoc(html));

describe("docToTelegramHtml", () => {
  it("roundtrips namespaced plugin shortcodes as chips without altering their namespace", () => {
    const html = "Hello {sample-tools.plan_label} and {a__plugin.offer-name}";
    expect(roundtrip(html)).toBe(html);
    const doc = telegramHtmlToDoc(html);
    expect(
      doc.content[0].content
        ?.filter((node) => node.type === "shortcode")
        .map((node) => node.attrs?.name)
    ).toEqual(["sample-tools.plan_label", "a__plugin.offer-name"]);
  });
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

describe("messageDisplayHtml", () => {
  it("keeps a legacy plain-text body literal and links what it contains", () => {
    const html = messageDisplayHtml("<b>not bold</b>\nsee https://x.dev", "text");
    expect(html).toContain("&lt;b&gt;not bold&lt;/b&gt;");
    expect(html).toContain('href="https://x.dev"');
  });

  it("splits a plain-text body into paragraphs on a blank line", () => {
    expect(messageDisplayHtml("one\n\ntwo", "text")).toBe("<p>one</p><p>two</p>");
  });

  it("renders only whitelisted markup from a rich body", () => {
    const html = messageDisplayHtml('<b>hi</b> <a href="https://x.dev">x</a>', "html");
    expect(html).toBe('<p><b>hi</b> <a href="https://x.dev">x</a></p>');
  });

  it("cannot emit a tag the parser does not know", () => {
    const html = messageDisplayHtml("<img src=x onerror=alert(1)>", "html");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("does not nest a detected link inside an authored one", () => {
    const html = messageDisplayHtml('<a href="https://a.dev">https://b.dev</a>', "html");
    expect(html.match(/<a /g)).toHaveLength(1);
  });

  it("shows an unsubstituted token as the characters it is", () => {
    expect(messageDisplayHtml("Hi {first_name}", "html")).toBe("<p>Hi {first_name}</p>");
  });

  it("emits a safe selectable emoji placeholder inside the original formatting", () => {
    const id = "5368324170671202286";
    const source = `<blockquote><a href="https://example.test"><b><tg-emoji emoji-id="${id}">👩🏽‍💻</tg-emoji></b></a></blockquote>`;
    expect(messageDisplayHtml(source, "html", { customEmoji: true })).toBe(
      `<blockquote><a href="https://example.test"><b><span class="rt-custom-emoji" data-custom-emoji-id="${id}"><span class="rt-custom-emoji-fallback">👩🏽‍💻</span></span></b></a></blockquote>`
    );
  });

  it("never creates media placeholders from plain text, code or pre", () => {
    const emoji = '<tg-emoji emoji-id="5368324170671202286">🙂</tg-emoji>';
    for (const [body, format] of [
      [emoji, "text"],
      [`<code>${emoji}</code>`, "html"],
      [`<pre>${emoji}</pre>`, "html"],
    ]) {
      const html = messageDisplayHtml(body, format, { customEmoji: true });
      expect(html).not.toContain('data-custom-emoji-id="');
      expect(html).toContain("🙂");
    }
  });

  it.each([
    '<tg-emoji emoji-id="1/../../secret">🙂</tg-emoji>',
    '<tg-emoji emoji-id="5368324170671202286" onclick="alert(1)">🙂</tg-emoji>',
    '<tg-emoji emoji-id="5368324170671202286"><img src="https://evil.test/tracker"></tg-emoji>',
    '<span class="rt-custom-emoji" data-custom-emoji-id="5368324170671202286"><span class="rt-custom-emoji-fallback">🙂</span></span>',
    '<img src="https://evil.test/tracker" onerror="alert(1)">',
  ])("does not turn untrusted markup into a media element: %s", (body) => {
    const html = messageDisplayHtml(body, "html", { customEmoji: true });
    expect(html).not.toContain("<img");
    expect(html).not.toContain('<span class="rt-custom-emoji"');
    expect(html).not.toContain("<tg-emoji");
  });
});

describe("wireTextLength", () => {
  it("counts what a reader sees, not the markup", () => {
    expect(wireTextLength("<b>abcd</b>", "html")).toBe(4);
    expect(wireTextLength('<a href="https://very.long/url">ok</a>', "html")).toBe(2);
    expect(wireTextLength("<b>abcd</b>", "text")).toBe("<b>abcd</b>".length);
  });
});

describe("Telegram custom emoji", () => {
  const id = "5368324170671202286";
  const entity = (fallback = "🙂", entityId = id) =>
    `<tg-emoji emoji-id="${entityId}">${fallback}</tg-emoji>`;

  it("retains an ID above the JavaScript integer range with neighboring tokens and links", () => {
    const wire = `Hi {first_name} ${entity("👩🏽‍💻")} <a href="https://example.test">open</a>`;
    const parsed = parseTelegramHtml(wire);
    expect(parsed.unknownTags).toEqual([]);
    expect(parsed.invalidCustomEmoji).toEqual([]);
    expect(parsed.doc.content[0]).toMatchObject({
      content: [
        { type: "text", text: "Hi " },
        { type: "shortcode", attrs: { name: "first_name" } },
        { type: "text", text: " " },
        { type: "customEmoji", attrs: { id, fallback: "👩🏽‍💻" } },
        { type: "text", text: " " },
        { type: "text", text: "open" },
      ],
    });
    expect(roundtrip(wire)).toBe(wire);
    expect(roundtrip(roundtrip(wire))).toBe(wire);
  });

  it("preserves supported surrounding marks and quote placement", () => {
    const wire = `<blockquote><a href="https://example.test"><b><i>${entity("❤️")}</i></b></a></blockquote>`;
    const schema = getSchema(composerExtensions(""));
    const document = schema.nodeFromJSON(telegramHtmlToDoc(wire));
    expect(docToTelegramHtml(document.toJSON() as Doc)).toBe(wire);
  });

  it.each(["🙂", "👩🏽‍💻", "👨‍👩‍👧‍👦", "❤️", "1️⃣", "🇷🇺", "🏳️‍🌈", "©", "®", "™", "☀"])(
    "keeps a whole Unicode emoji fallback: %s",
    (fallback) => {
      expect(isCustomEmojiFallback(fallback)).toBe(true);
      expect(roundtrip(entity(fallback))).toBe(entity(fallback));
      expect(wireTextLength(entity(fallback))).toBe([...fallback].length);
    }
  );

  it.each(["", "0", "01", "-1", "1.2", "1e18", "9007199254740993x", "123456789012345678901"])(
    "shows an invalid ID as literal source with a warning: %s",
    (invalidId) => {
      expect(isCustomEmojiId(invalidId)).toBe(false);
      const wire = entity("🙂", invalidId);
      const parsed = parseTelegramHtml(wire);
      expect(parsed.invalidCustomEmoji).toEqual([wire]);
      expect(docToTelegramHtml(parsed.doc)).toBe(wire.replace(/</g, "&lt;").replace(/>/g, "&gt;"));
      expect(messageDisplayHtml(wire, "html")).not.toContain("<tg-emoji");
    }
  );

  it.each([
    "",
    "ordinary text",
    "🙂🙂",
    " 🙂",
    "<img src=x onerror=alert(1)>",
    "🙂\n",
    "😀́",
    "😀‍",
    "🇷",
  ])("does not create an entity from an invalid fallback: %s", (fallback) => {
    expect(isCustomEmojiFallback(fallback)).toBe(false);
    expect(parseTelegramHtml(entity(fallback)).invalidCustomEmoji).not.toEqual([]);
  });

  it("rejects nested HTML, extra attributes, unclosed wrappers and orphan closing tags", () => {
    for (const wire of [
      `<tg-emoji emoji-id="${id}"><b>🙂</b></tg-emoji>`,
      `<tg-emoji emoji-id="${id}" onclick="alert(1)">🙂</tg-emoji>`,
      `<tg-emoji emoji-id="${id}">${entity()}</tg-emoji>`,
      `<tg-emoji emoji-id="${id}">🙂`,
      "🙂</tg-emoji>",
    ]) {
      const parsed = parseTelegramHtml(wire);
      expect(parsed.invalidCustomEmoji.length).toBeGreaterThan(0);
      expect(docToTelegramHtml(parsed.doc)).not.toContain("<tg-emoji");
      expect(previewHtmlFromWire(wire)).not.toContain("<tg-emoji");
    }
  });

  it("decodes numeric Unicode entities once and canonicalizes source attributes", () => {
    expect(roundtrip(`<tg-emoji emoji-id='${id}'>&#x1f642;</tg-emoji>`)).toBe(entity());
    expect(roundtrip(`<tg-emoji emoji-id=${id}>&#128578;</tg-emoji>`)).toBe(entity());
    expect(roundtrip("&#38;lt;b&#38;gt;")).toBe("&amp;lt;b&amp;gt;");
  });

  it("uses plain fallback in code and pre without losing surrounding content", () => {
    expect(roundtrip(`<code>a${entity("👩🏽‍💻")}b</code>`)).toBe("<code>a👩🏽‍💻b</code>");
    expect(roundtrip(`<pre>a${entity("❤️")}\nb</pre>`)).toBe("<pre>a❤️\nb</pre>");
    expect(roundtrip(`<pre>a${entity("❤️")}`)).toBe("<pre>a❤️</pre>");
  });

  it("renders Unicode fallback safely in both browser surfaces", () => {
    const wire = `<b>${entity()}</b><img src=x onerror=alert(1)>`;
    for (const html of [previewHtmlFromWire(wire), messageDisplayHtml(wire, "html")]) {
      expect(html).toContain("<b>🙂</b>");
      expect(html).not.toContain("<tg-emoji");
      expect(html).not.toContain("<img");
    }
    const invalidDocument: Doc = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            {
              type: "customEmoji",
              attrs: { id: '" onclick="alert(1)', fallback: "<script>alert(1)</script>" },
            },
          ],
        },
      ],
    };
    expect(docToTelegramHtml(invalidDocument)).toBe("&lt;script&gt;alert(1)&lt;/script&gt;");
  });

  it("counts fallback codepoints consistently with ordinary text", () => {
    expect(wireTextLength(`A${entity("👩🏽‍💻")}Z`)).toBe(6);
    expect(wireTextLength("A👩🏽‍💻Z", "text")).toBe(6);
    expect(wireTextLength(`<pre>🙂${entity("❤️")}</pre>`)).toBe(3);
  });

  it("keeps the atom through copied slices, whole-node deletion, undo and redo", () => {
    const schema = getSchema(composerExtensions(""));
    let state = EditorState.create({
      schema,
      doc: schema.nodeFromJSON(telegramHtmlToDoc(`A${entity()}Z`)),
      plugins: [history()],
    });
    const atom = state.doc.nodeAt(2);
    expect(atom?.isAtom).toBe(true);
    expect(atom?.nodeSize).toBe(1);
    const copied = state.doc.slice(2, 3);
    state = state.apply(
      state.tr.setSelection(NodeSelection.create(state.doc, 2)).deleteSelection()
    );
    expect(docToTelegramHtml(state.doc.toJSON() as Doc)).toBe("AZ");
    expect(
      undo(state, (transaction) => {
        state = state.apply(transaction);
      })
    ).toBe(true);
    expect(docToTelegramHtml(state.doc.toJSON() as Doc)).toBe(`A${entity()}Z`);
    expect(
      redo(state, (transaction) => {
        state = state.apply(transaction);
      })
    ).toBe(true);
    state = state.apply(
      state.tr.setSelection(TextSelection.create(state.doc, 2)).replaceSelection(copied)
    );
    expect(docToTelegramHtml(state.doc.toJSON() as Doc)).toBe(`A${entity()}Z`);
  });
});
