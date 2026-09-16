import { describe, expect, it } from "vitest";

import { themeTokensToInlineStyle } from "./themeStyle.js";

describe("themeTokensToInlineStyle", () => {
  it("quotes the separator token as a CSS string", () => {
    expect(themeTokensToInlineStyle({ separator: "|" })).toContain('--separator:"|"');
  });

  it("keeps an empty separator so a theme can drop the separator", () => {
    expect(themeTokensToInlineStyle({ separator: "" })).toContain('--separator:""');
  });

  it("omits the separator when the theme does not define it", () => {
    expect(themeTokensToInlineStyle({ color_scheme: "dark" })).not.toContain("--separator:");
  });

  it("ignores separator values with control characters", () => {
    expect(themeTokensToInlineStyle({ separator: "a\nb" })).not.toContain("--separator:");
  });
});
