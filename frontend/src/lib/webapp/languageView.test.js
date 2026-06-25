import { describe, expect, it } from "vitest";

import { computeLanguageView } from "./languageView.js";

describe("computeLanguageView", () => {
  it("uses webapp defaults before configured and i18n-only languages", () => {
    const view = computeLanguageView({
      cfgLanguages: [{ code: "de", label: "Deutsch custom", flag: "DE" }],
      currentLang: "de",
      i18nMessages: { fr: {}, es: {} },
    });

    expect(view.languageCodes).toEqual(["ru", "en", "de", "fr", "es"]);
    expect(view.currentLanguageOption).toEqual({
      value: "de",
      label: "Deutsch custom",
      flag: "DE",
    });
  });

  it("falls back to built-in labels and flags", () => {
    const view = computeLanguageView({
      cfgLanguages: [],
      currentLang: "en",
      i18nMessages: {},
    });

    expect(view.languageOptions[1]).toEqual({
      value: "en",
      label: "English",
      flag: "\u{1F1EC}\u{1F1E7}",
    });
    expect(view.currentLanguageOption?.value).toBe("en");
  });

  it("adds the current language when it is not otherwise configured", () => {
    const view = computeLanguageView({
      cfgLanguages: [],
      currentLang: "it",
      i18nMessages: {},
    });

    expect(view.languageCodes).toEqual(["ru", "en", "it"]);
    expect(view.currentLanguageOption).toEqual({
      value: "it",
      label: "IT",
      flag: "\u{1F3F3}\uFE0F",
    });
  });
});
