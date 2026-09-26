import { describe, expect, it } from "vitest";

import { renderMarkdown } from "./markdown.js";

describe("renderMarkdown", () => {
  it("renders normal nested Markdown without enabling raw HTML", () => {
    const html = renderMarkdown(
      "# Title\n\nA [**safe** link](https://example.com).\n\n- one\n- two"
    );

    expect(html).toContain("<h1>Title</h1>");
    expect(html).toContain("<strong>safe</strong>");
    expect(html).toContain('href="https://example.com"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("<ul>");
  });

  it("escapes raw elements and event attributes instead of injecting them", () => {
    const html = renderMarkdown('<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">');

    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img src=x");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("onerror=&quot;alert(1)&quot;");
  });

  it("drops unsafe link and image destinations", () => {
    const html = renderMarkdown(
      "[bad **link**](javascript:alert(1))\n\n![bad image](javascript:alert(1))"
    );

    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("<img");
    expect(html).toContain("<strong>link</strong>");
    expect(html).toContain("bad image");
  });
});
