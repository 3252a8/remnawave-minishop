import { describe, expect, it } from "vitest";

import { selectedThemeVariant } from "./themeEditorContext";

describe("selectedThemeVariant", () => {
  it("keeps the editor context local without changing the persisted variant", () => {
    expect(selectedThemeVariant("light", "dark")).toBe("light");
    expect(selectedThemeVariant(undefined, "dark")).toBe("dark");
  });
});
