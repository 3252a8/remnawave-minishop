import { describe, expect, it } from "vitest";

import { readFileSync } from "node:fs";
import {
  colorInputOpacity,
  colorInputValueChanged,
  colorInputWithOpacity,
  normalizeColorInput,
} from "./colorInputValue";

describe("colorInputValueChanged", () => {
  it("ignores the color picker's initial event", () => {
    expect(colorInputValueChanged("#AABBCC", "#aabbcc")).toBe(false);
  });

  it("accepts an actual user color edit", () => {
    expect(colorInputValueChanged("#aabbcc", "#aabbcd")).toBe(true);
  });

  it("does not dirty a setting when the picker expands an equivalent HEX value", () => {
    expect(colorInputValueChanged("#abc", "#aabbcc")).toBe(false);
    expect(colorInputValueChanged("#aabbccff", "#aabbcc")).toBe(false);
    expect(colorInputValueChanged("#abcd", "#aabbccdd")).toBe(false);
    expect(colorInputValueChanged("#aabbcc80", "#aabbcc")).toBe(true);
  });

  it("keeps alpha only for fields which support it", () => {
    expect(normalizeColorInput(" ABC8 ")).toBe("#aabbcc88");
    expect(normalizeColorInput("#12345600", false)).toBe("#123456");
    expect(normalizeColorInput("#12345")).toBeNull();
  });

  it("preserves RGB at zero opacity and restores an opaque HEX at 100 percent", () => {
    expect(colorInputWithOpacity("#123456", 0)).toBe("#12345600");
    expect(colorInputWithOpacity("#12345600", 100)).toBe("#123456");
    expect(colorInputWithOpacity("#123456", 50)).toBe("#12345680");
    expect(colorInputOpacity("#12345680")).toBe(50);
    expect(colorInputOpacity("#12345600")).toBe(0);
  });

  it("translates every shared picker label in both base locales", () => {
    const source = readFileSync(new URL("./color-input.svelte", import.meta.url), "utf8");
    const keys = [...source.matchAll(/\btext\("([a-z_]+)"/g)].map((match) => match[1]);
    expect(keys.length).toBeGreaterThan(0);
    for (const language of ["ru", "en"]) {
      const locale = JSON.parse(
        readFileSync(new URL(`../../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      for (const key of keys) expect(locale[`admin_color_picker_${key}`]).toBeTruthy();
    }
  });
});
