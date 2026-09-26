type Scope = "webapp" | "admin";
type Messages = Record<string, Record<string, unknown>>;
type I18nResponse = { ok?: boolean; i18n?: Messages } | null;

export function createLanguageScopeLoader({
  initialLanguages,
  normalizeLanguage,
  fetchScope,
  mergeMessages,
}: {
  initialLanguages: string[];
  normalizeLanguage: (language: string) => string;
  fetchScope: (scope: Scope, language: string) => Promise<I18nResponse>;
  mergeMessages: (messages: Messages) => void;
}) {
  const loaded = new Set(initialLanguages.map((language) => `webapp:${language}`));
  const inFlight = new Map<string, Promise<void>>();

  function load(scope: Scope, requestedLanguage: string, fresh = false): Promise<void> {
    const language = normalizeLanguage(requestedLanguage);
    const key = `${scope}:${language}`;
    if (!fresh && loaded.has(key)) return Promise.resolve();
    const existing = inFlight.get(key);
    if (existing) return existing;

    const flight = fetchScope(scope, language)
      .then((payload) => {
        const bucket = payload?.i18n?.[language];
        if (!payload?.ok || !bucket) throw new Error(`i18n_load_failed:${key}`);
        mergeMessages({ [language]: bucket });
        loaded.add(key);
      })
      .finally(() => {
        inFlight.delete(key);
      });
    inFlight.set(key, flight);
    return flight;
  }

  return { load };
}

export function rememberWebappLanguage(language: string): void {
  if (typeof document === "undefined" || typeof window === "undefined") return;
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `minishop_lang=${encodeURIComponent(language)}; Path=/; Max-Age=31536000; SameSite=Lax${secure}`;
}
