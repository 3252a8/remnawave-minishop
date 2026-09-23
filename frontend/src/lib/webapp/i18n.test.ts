import { describe, expect, it } from "vitest";

import { createI18n } from "./i18n.js";

describe("i18n language loading", () => {
  it("accepts a configured language before its dictionary has loaded", () => {
    let selectedLanguage = "ru";
    const i18n = createI18n({
      messages: { ru: { wa_title: "Название" } },
      supportedLanguages: ["ru", "it"],
      getLang: () => selectedLanguage,
    });

    expect(i18n.normalizeLangCode("it")).toBe("it");
    selectedLanguage = "it";
    i18n.mergeMessages({ it: { wa_title: "Titolo" } });
    expect(i18n.t("wa_title")).toBe("Titolo");
  });
});
