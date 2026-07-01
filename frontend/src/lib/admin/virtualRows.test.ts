import { describe, expect, it } from "vitest";

import { calculateVirtualRange } from "./virtualRows";

describe("calculateVirtualRange", () => {
  it("keeps the range within the available rows", () => {
    expect(
      calculateVirtualRange({
        rowCount: 100,
        rowHeight: 50,
        viewportHeight: 200,
        offsetTop: -5000,
        overscan: 4,
      })
    ).toEqual({ start: 96, end: 100 });
  });

  it("adds overscan before and after visible rows", () => {
    expect(
      calculateVirtualRange({
        rowCount: 100,
        rowHeight: 50,
        viewportHeight: 200,
        offsetTop: -250,
        overscan: 2,
      })
    ).toEqual({ start: 3, end: 11 });
  });
});
