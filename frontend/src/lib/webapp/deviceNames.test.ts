import { describe, expect, it } from "vitest";
import { normalizeDeviceName } from "./deviceNames";

describe("device name normalization", () => {
  it("removes invisible formatting and surrogate characters before counting", () => {
    expect(normalizeDeviceName("x".repeat(32) + "\u202e\u200b\ufeff\ud800")).toBe("x".repeat(32));
    expect(normalizeDeviceName("  Work\n\tlaptop\u2028  ")).toBe("Work laptop");
  });

  it("preserves joiners used by emoji and writing systems", () => {
    const family = "\u{1f468}\u200d\u{1f469}\u200d\u{1f467}";
    expect(normalizeDeviceName(family + " tablet")).toBe(family + " tablet");
    expect(normalizeDeviceName("a\u200cb")).toBe("a\u200cb");
  });

  it("composes combining marks after removing invisible formatting", () => {
    expect(normalizeDeviceName("Cafe\u0301")).toBe("Caf\u00e9");
    expect(normalizeDeviceName("e\u202e\u0301")).toBe("\u00e9");
  });
});
