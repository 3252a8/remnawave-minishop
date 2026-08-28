import { describe, expect, it } from "vitest";

import {
  createMenuButtonDraft,
  parseMenuButtonDrafts,
  reorderMenuButtonDrafts,
  serializeMenuButtonDrafts,
} from "./menuButtons.js";

describe("menu button drafts", () => {
  it("round-trips localized menu buttons", () => {
    const button = createMenuButtonDraft(["ru", "en"]);
    button.labels = { ru: "Помощь", en: "Help" };
    button.kind = "telegram";
    button.target = "https://t.me/help";

    expect(parseMenuButtonDrafts(serializeMenuButtonDrafts([button]))).toEqual({
      buttons: [button],
      invalid: false,
    });
  });

  it("reports malformed persisted JSON", () => {
    expect(parseMenuButtonDrafts("{oops")).toEqual({ buttons: [], invalid: true });
  });

  it("reorders buttons without mutating the source", () => {
    const first = createMenuButtonDraft(["en"]);
    const second = createMenuButtonDraft(["en"]);
    const source = [first, second];

    expect(reorderMenuButtonDrafts(source, 0, 1)).toEqual([second, first]);
    expect(source).toEqual([first, second]);
  });
});
