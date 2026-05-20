import { LANGUAGE_LABELS } from "./constants.js";
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
    const key = String(lang || "")
      .trim()
      .toLowerCase();
    if (!key) return defaultLang;
    const base = key.split("-")[0];
    if (LANGUAGE_LABELS[base]) return base;
    if (messages[base]) return base;
    if (messages[key]) return key;
    return defaultLang;
  }

  function currentLang() {
    return normalizeLangCode(typeof getLang === "function" ? getLang() : defaultLang);
  }

  function t(key, params = {}, fallback = "") {
    const lang = currentLang();
    const variants = [
      messages?.[lang]?.[key],
      messages?.en?.[key],
      messages?.ru?.[key],
      fallback,
      key,
    ];
    const raw = variants.find((value) => typeof value === "string" && value.length);
    return formatTemplate(raw, params);
  }

  function languageName(code) {
    const key = String(code || "")
      .trim()
      .toLowerCase();
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
