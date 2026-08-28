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

    expect(button.show_in_bot).toBe(true);
    expect(button.show_in_webapp).toBe(true);

    expect(parseMenuButtonDrafts(serializeMenuButtonDrafts([button]))).toEqual({
      buttons: [button],
      invalid: false,
    });
  });

  it("reports malformed persisted JSON", () => {
    expect(parseMenuButtonDrafts("{oops")).toEqual({ buttons: [], invalid: true });
  });

  it("defaults legacy buttons to both menus and preserves explicit visibility", () => {
    const parsed = parseMenuButtonDrafts(
      JSON.stringify([
        {
          id: "legacy",
          kind: "external",
          target: "https://example.com",
          icon: "",
          labels: { en: "Legacy" },
          show_in_webapp: false,
        },
      ])
    );

    expect(parsed.buttons[0]).toMatchObject({
      show_in_bot: true,
      show_in_webapp: false,
    });
  });

  it("reorders buttons without mutating the source", () => {
    const first = createMenuButtonDraft(["en"]);
    const second = createMenuButtonDraft(["en"]);
    const source = [first, second];

    expect(reorderMenuButtonDrafts(source, 0, 1)).toEqual([second, first]);
    expect(source).toEqual([first, second]);
  });
});
