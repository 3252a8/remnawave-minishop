import {
  LANGUAGE_FLAGS,
  LANGUAGE_LABELS,
  uniqueLanguageCodes,
  WEBAPP_LANGUAGE_ORDER,
} from "./constants.js";

const DEFAULT_LANGUAGE_FLAG = "\u{1F3F3}\uFE0F";

type WebappRecord = Record<string, unknown>;

type ServerLanguage = {
  code?: string;
  flag?: string;
  label?: string;
};

export type LanguageOption = {
  flag: string;
  label: string;
  value: string;
};

export interface LanguageView {
  currentLanguageOption: LanguageOption | undefined;
  languageCodes: string[];
  languageOptions: LanguageOption[];
}

export interface LanguageViewInput {
  cfgLanguages: unknown;
  currentLang: string;
  i18nMessages: WebappRecord | null | undefined;
}

function serverLanguages(value: unknown): ServerLanguage[] {
  return Array.isArray(value) ? (value as ServerLanguage[]) : [];
}

export function computeLanguageView({
  cfgLanguages,
  currentLang,
  i18nMessages,
}: LanguageViewInput): LanguageView {
  const configuredLanguages = serverLanguages(cfgLanguages);
  const languageCodes = uniqueLanguageCodes(
    WEBAPP_LANGUAGE_ORDER,
    configuredLanguages,
    Object.keys(i18nMessages || {}),
    [currentLang]
  );
  const languageLabels = LANGUAGE_LABELS as Record<string, string>;
  const languageFlags = LANGUAGE_FLAGS as Record<string, string>;
  const languageOptions = languageCodes.map((code) => {
    const serverLanguage = configuredLanguages.find((language) => language.code === code);
    return {
      value: code,
      label: serverLanguage?.label || languageLabels[code] || code.toUpperCase(),
      flag: serverLanguage?.flag || languageFlags[code] || DEFAULT_LANGUAGE_FLAG,
    };
  });
  return {
    currentLanguageOption:
      languageOptions.find((option) => option.value === currentLang) || languageOptions[0],
    languageCodes,
    languageOptions,
  };
}
