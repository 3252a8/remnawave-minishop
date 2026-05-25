import { LANGUAGE_LABELS, normalizeLanguageCode, resolveLocaleKey } from "./constants.js";
import { formatTemplate, formatFraction, roundToHalf } from "./formatters.js";
import { unitPluralBucket } from "./plurals.js";

export function createI18n({
  messages: initialMessages = {},
  defaultLang = "ru",
  getLang = null,
} = {}) {
  const messages = {};

  function mergeMessages(nextMessages = {}) {
    if (!nextMessages || typeof nextMessages !== "object") return messages;
    for (const [lang, bucket] of Object.entries(nextMessages)) {
      if (!bucket || typeof bucket !== "object") continue;
      messages[lang] = { ...(messages[lang] || {}), ...bucket };
    }
    return messages;
  }

  mergeMessages(initialMessages);

  function normalizeLangCode(lang) {
    const key = normalizeLanguageCode(lang);
    if (!key) return defaultLang;
    const base = key.split("-")[0];
    if (messages[key]) return key;
    if (messages[base]) return base;
    if (LANGUAGE_LABELS[key]) return key;
    if (LANGUAGE_LABELS[base]) return base;
    return defaultLang;
  }

  function currentLang() {
    return normalizeLangCode(typeof getLang === "function" ? getLang() : defaultLang);
  }

  function t(key, params = {}, fallback = "") {
    const lang = currentLang();
    const lookupKey = resolveLocaleKey(key);
    const variants = [
      messages?.[lang]?.[lookupKey],
      messages?.en?.[lookupKey],
      messages?.ru?.[lookupKey],
      fallback,
      key,
    ];
    const raw = variants.find((value) => typeof value === "string" && value.length);
    return formatTemplate(raw, params);
  }

  function languageName(code) {
    const key = normalizeLanguageCode(code);
    if (!key) return t("wa_language_default");
    return LANGUAGE_LABELS[key] || key.toUpperCase();
  }

  function termUnitLabel(value, unit) {
    const bucket = unitPluralBucket(value, currentLang());
    return t(`wa_sub_term_${unit}_${bucket}`);
  }

  return { normalizeLangCode, t, currentLang, languageName, termUnitLabel, mergeMessages };
}

export { formatFraction, roundToHalf };
