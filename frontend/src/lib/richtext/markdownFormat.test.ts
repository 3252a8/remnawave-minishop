import { describe, expect, it } from "vitest";

import { markdownFormat } from "./markdownFormat.js";

describe("markdownFormat", () => {
  it("round-trips document blocks and inline Markdown through the shared editor format", () => {
    const markdown = [
      "# Privacy policy",
      "",
      "- First condition",
      "- [Service](https://example.test) condition",
      "",
      "> A quoted **notice**",
      "",
      "```",
      "const allowed = true;",
      "```",
    ].join("\n");

    expect(markdownFormat.toSource(markdownFormat.fromSource(markdown))).toBe(markdown);
  });

  it("keeps Markdown storage separate from the Telegram HTML editor format", () => {
    const markdown = "# PRIVACY_POLICY_URL\n\n**Bold** and ~~struck~~ with `code`";

    const saved = markdownFormat.toSource(markdownFormat.fromSource(markdown));

    expect(saved).toBe(markdown);
    expect(saved).not.toContain("<b>");
    expect(saved).not.toContain("<pre>");
  });

  it("disables HTML-only source controls and underline for public Markdown", () => {
    expect(markdownFormat.sourceModeControls).toBe(false);
    expect(markdownFormat.enabledMarks).not.toContain("underline");
  });

  it("creates an editable empty paragraph so the visual editor can show its placeholder", () => {
    const document = markdownFormat.fromSource("");

    expect(document).toEqual({ type: "doc", content: [{ type: "paragraph", content: [] }] });
    expect(markdownFormat.toSource(document)).toBe("");
  });

  it.each([
    "![Logo](https://example.test/logo.png)",
    "![Logo][logo]\n\n[logo]: https://example.test/logo.png",
    "| Item | Value |\n| --- | --- |\n| **One** | Two |",
    "- [x] Done\n- [ ] Pending",
    "```js\nconst allowed = true;\n```",
    "---",
    '<div class="note">Raw HTML</div>',
    '[Service](https://example.test "Title")',
    "`a*b` and `` `value` ``",
    "\\_literal\\_",
  ])("preserves document content through visual editing: %s", (source) => {
    expect(markdownFormat.toSource(markdownFormat.fromSource(source))).toBe(source);
  });
});
