import { describe, expect, it } from "vitest";

import {
  normalizeAppearanceRadius,
  normalizeAppearanceTransparency,
  radiusToken,
  transparencyToken,
} from "./appearanceSliders";

describe("appearance slider normalization", () => {
  it("uses only valid px radius tokens and canonical slider bounds", () => {
    expect(normalizeAppearanceRadius("10.6px")).toBe(11);
    expect(normalizeAppearanceRadius("-4px")).toBe(4);
    expect(normalizeAppearanceRadius("28px")).toBe(28);
    expect(radiusToken(-4)).toBe("4px");
    expect(radiusToken(29.2)).toBe("28px");
    expect(radiusToken("")).toBeNull();
    expect(normalizeAppearanceRadius("-4px", 8, 0)).toBe(0);
    expect(radiusToken(-4, 0)).toBe("0px");
  });

  it("does not treat empty transparency as zero", () => {
    expect(normalizeAppearanceTransparency(undefined)).toBe(100);
    expect(normalizeAppearanceTransparency("")).toBe(100);
    expect(normalizeAppearanceTransparency("42.6")).toBe(43);
    expect(transparencyToken(-1)).toBe(0);
    expect(transparencyToken(101)).toBe(100);
  });
});
