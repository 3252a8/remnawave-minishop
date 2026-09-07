import { describe, expect, it } from "vitest";

import { isReversalReasonValid } from "./reversalReason.js";

describe("reversal reason validation", () => {
  it("requires at least three non-whitespace characters by default", () => {
    expect(isReversalReasonValid("  no  ", false)).toBe(false);
    expect(isReversalReasonValid("  duplicate  ", false)).toBe(true);
  });

  it("allows an empty reason only when explicitly requested", () => {
    expect(isReversalReasonValid("   ", true)).toBe(true);
  });
});
