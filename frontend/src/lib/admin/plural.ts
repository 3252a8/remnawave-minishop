type AdminTranslator = (key: string, params?: Record<string, unknown>, fallback?: string) => string;

/**
 * Picks the `<base>_one|_few|_many` admin key for `count` using the locale's plural
 * rules (`period_plural_locale` names it, so ru gets one/few/many and en one/other).
 */
export function atPlural(
  at: AdminTranslator,
  base: string,
  count: number,
  params: Record<string, unknown> = {},
  fallback = ""
): string {
  const language = at("period_plural_locale", {}, "en");
  let category: string;
  try {
    category = new Intl.PluralRules(language).select(count);
  } catch {
    category = count === 1 ? "one" : "many";
  }
  const form = category === "one" || category === "few" ? category : "many";
  return at(`${base}_${form}`, { count, ...params }, fallback || `${count}`);
}
