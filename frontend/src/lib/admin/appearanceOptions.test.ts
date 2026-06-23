import { describe, expect, it } from "vitest";

import {
  DEFAULT_THEME_PRESETS,
  DEFAULT_THEME_VARIANTS,
  FONT_OPTIONS,
  MONO_FONT_OPTIONS,
  googleMonoFontStack,
  googleSansFontStack,
} from "./appearanceOptions";

describe("appearanceOptions", () => {
  it("builds Google font stacks with stable fallbacks", () => {
    expect(googleSansFontStack("Open Sans")).toBe(
      '"Open Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif'
    );
    expect(googleSansFontStack("Roboto")).toBe(
      'Roboto, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif'
    );
    expect(googleMonoFontStack("JetBrains Mono")).toBe(
      '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
    );
  });

  it("keeps font option values aligned with generated stacks", () => {
    expect(FONT_OPTIONS.find((item) => item.label === "Open Sans")?.value).toBe(
      googleSansFontStack("Open Sans")
    );
    expect(MONO_FONT_OPTIONS.find((item) => item.label === "JetBrains Mono")?.value).toBe(
      googleMonoFontStack("JetBrains Mono")
    );
  });

  it("keeps default presets partitioned by theme variant", () => {
    expect(DEFAULT_THEME_VARIANTS).toEqual(["dark", "light"]);

    for (const variant of DEFAULT_THEME_VARIANTS) {
      expect(DEFAULT_THEME_PRESETS[variant].length).toBeGreaterThan(0);
      expect(
        DEFAULT_THEME_PRESETS[variant].every((preset) => preset.tokens.color_scheme === variant)
      ).toBe(true);
    }
  });
});
