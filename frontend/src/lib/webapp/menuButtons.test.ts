import { describe, expect, it } from "vitest";

import { visibleMenuButtons } from "./menuButtons.js";

describe("menu button visibility", () => {
  const buttons = [
    { id: "everywhere", show_in_telegram_webapp: true, show_in_browser: true },
    { id: "telegram", show_in_telegram_webapp: true, show_in_browser: false },
    { id: "browser", show_in_telegram_webapp: false, show_in_browser: true },
    { id: "hidden", show_in_telegram_webapp: false, show_in_browser: false },
    { id: "legacy" },
  ];

  it("shows only Telegram Mini App buttons in Telegram", () => {
    expect(visibleMenuButtons(buttons, true).map((button) => button.id)).toEqual([
      "everywhere",
      "telegram",
      "legacy",
    ]);
  });

  it("shows only browser buttons outside Telegram", () => {
    expect(visibleMenuButtons(buttons, false).map((button) => button.id)).toEqual([
      "everywhere",
      "browser",
      "legacy",
    ]);
  });
});
