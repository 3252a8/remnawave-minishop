import { describe, it, expect } from "vitest";
import { csvHeader } from "./csvHeader";

describe("advertising CSV mapping", () => {
  it("preserves quoted delimiters, escaped quotes, BOM and empty columns", () => {
    expect(csvHeader('\uFEFFstart;"ad,name";"say ""hello""";;cost\r\nrow', ";")).toEqual([
      "start",
      "ad,name",
      'say "hello"',
      "",
      "cost",
    ]);
  });
  it("uses the chosen delimiter and rejects an incomplete quoted header", () => {
    expect(csvHeader("start\tad,name\tcost\nrow", "\t")).toEqual(["start", "ad,name", "cost"]);
    expect(csvHeader('start,"incomplete', ",")).toEqual([]);
  });
});
