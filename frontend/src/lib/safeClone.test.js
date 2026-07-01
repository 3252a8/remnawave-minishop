import { describe, expect, it } from "vitest";

import { structuredCloneSafe } from "./safeClone.js";

describe("structuredCloneSafe", () => {
  it("keeps JSON-like data when native and JSON cloning cannot handle transient values", () => {
    const hostLike = Object.assign(Object.create({ host: true }), { label: "window" });
    const payload = {
      count: 2,
      nested: { amount: 99 },
      hostLike,
      onClick: () => {},
    };
    payload.self = payload;

    expect(structuredCloneSafe(payload)).toEqual({
      count: 2,
      nested: { amount: 99 },
    });
  });
});
