import { describe, expect, it } from "vitest";

import { colorInputValueChanged } from "./colorInputValue";

describe("colorInputValueChanged", () => {
  it("ignores the color picker's initial event", () => {
    expect(colorInputValueChanged("#AABBCC", "#aabbcc")).toBe(false);
  });

  it("accepts an actual user color edit", () => {
    expect(colorInputValueChanged("#aabbcc", "#aabbcd")).toBe(true);
  });
});
