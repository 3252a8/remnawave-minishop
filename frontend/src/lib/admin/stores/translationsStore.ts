import { writable, type Writable } from "svelte/store";
import { adminErrorMessage } from "../errors.js";
import { unwrap, type ApiResponse, type GetResponse } from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";

type AdminErrorResponse = {
  ok?: false;
  error?: string;
  message?: string;
  detail?: string;
  errors?: Record<string, unknown>;
};
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TranslationsResponse = GetResponse<"/api/admin/translations">;
type TranslationsPatchPayload = components["schemas"]["AdminTranslationsPatchBody"];
type TranslationsPatchResponse = Extract<
  ApiResponse<"/api/admin/translations">,
  { applied: number }
>;

export type TranslationLanguage = {
  code: string;
  label: string;
  base?: boolean;
};
export type TranslationValue = {
  base?: string;
  fallback?: string;
  effective?: string;
  override?: string;
  overridden?: boolean;
};
export type TranslationItem = {
  key: string;
  audience?: string;
  values?: Record<string, TranslationValue>;
};
export type TranslationGroup = {
  id: string;
  title: string;
  title_key?: string;
  description?: string;
  description_key?: string;
  audience?: string;
  items?: TranslationItem[];
};
export type TranslationDirtyEntry = {
  lang: string;
  key: string;
  value: string;
  deleted: boolean;
};
export type TranslationDirtyState = Record<string, TranslationDirtyEntry>;
export type TranslationDelete = { lang: string; key: string };
export type TranslationUpdates = Record<string, Record<string, string>>;
export type TranslationsSavedPayload = {
  updates: TranslationUpdates;
  deletes: TranslationDelete[];
};
type TranslationsState = {
  translationGroups: TranslationGroup[];
  translationLanguages: TranslationLanguage[];
  translationsLoading: boolean;
  translationsDirty: TranslationDirtyState;
  translationsSaving: boolean;
  translationsPath: string;
  translationsOverrideCount: number;
};
type TranslationsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type TranslationsStore = Writable<TranslationsState> & {
  loadTranslations: () => Promise<void>;
  markDirty: (lang: string, key: string, value: string, deleted?: boolean) => void;
  clearDirty: (lang: string, key: string) => void;
  resetField: (lang: string, key: string, overridden: boolean) => void;
  addTranslationLanguage: (rawCode: string) => boolean;
  saveTranslations: (
    onTranslationsSaved?: (payload: TranslationsSavedPayload) => void | Promise<void>
  ) => Promise<boolean>;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

function dirtyId(lang: string, key: string): string {
  return `${lang}:${key}`;
}

function normalizeLanguageCode(value: string): string {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-");
}

function isValidLanguageCode(value: string): boolean {
  return /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(value) && value.length >= 2 && value.length <= 16;
}

function languageLabel(code: string): string {
  const labels: Record<string, string> = {
    ru: "Русский",
    en: "English",
    de: "Deutsch",
    es: "Español",
    fr: "Français",
    "pt-br": "Português (BR)",
    uk: "Українська",
  };
  return labels[code] || code.toUpperCase();
}

function normalizeGroups(groups: unknown): TranslationGroup[] {
  return Array.isArray(groups) ? (groups as TranslationGroup[]) : [];
}

function normalizeLanguages(languages: unknown): TranslationLanguage[] {
  return Array.isArray(languages) ? (languages as TranslationLanguage[]) : [];
}

export function createTranslationsStore({
  api,
  onToast,
  at,
}: TranslationsStoreOptions): TranslationsStore {
  const state: Writable<TranslationsState> = writable({
    translationGroups: [],
    translationLanguages: [],
    translationsLoading: false,
    translationsDirty: {},
    translationsSaving: false,
    translationsPath: "",
    translationsOverrideCount: 0,
  });

  async function loadTranslations(): Promise<void> {
    state.update((s) => ({ ...s, translationsLoading: true, translationsDirty: {} }));
    try {
      const data = (await api("/admin/translations")) as TranslationsResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        state.update((s) => ({
          ...s,
          translationGroups: normalizeGroups(result.groups),
          translationLanguages: normalizeLanguages(result.languages),
          translationsPath: result.path || "",
          translationsOverrideCount: result.override_count || 0,
        }));
      }
    } finally {
      state.update((s) => ({ ...s, translationsLoading: false }));
    }
  }

  function markDirty(lang: string, key: string, value: string, deleted = false): void {
    state.update((s) => ({
      ...s,
      translationsDirty: {
        ...s.translationsDirty,
        [dirtyId(lang, key)]: { lang, key, value, deleted },
      },
    }));
  }

  function clearDirty(lang: string, key: string): void {
    state.update((s) => {
      const next = { ...s.translationsDirty };
      delete next[dirtyId(lang, key)];
      return { ...s, translationsDirty: next };
    });
  }

  function resetField(lang: string, key: string, overridden: boolean): void {
    if (overridden) {
      markDirty(lang, key, "", true);
    } else {
      clearDirty(lang, key);
    }
  }

  function addTranslationLanguage(rawCode: string): boolean {
    const code = normalizeLanguageCode(rawCode);
    if (!isValidLanguageCode(code)) {
      onToast(at("translations_language_invalid", {}, "Invalid language code"));
      return false;
    }
    let exists = false;
    state.update((s) => {
      exists = (s.translationLanguages || []).some((lang) => lang.code === code);
      if (exists) return s;
      return {
        ...s,
        translationLanguages: [
          ...(s.translationLanguages || []),
          { code, label: languageLabel(code), base: false },
        ].sort((a, b) => a.code.localeCompare(b.code)),
      };
    });
    if (exists) {
      onToast(at("translations_language_exists", { code }, `${code} already exists`));
      return false;
    }
    return true;
  }

  async function saveTranslations(
    onTranslationsSaved?: (payload: TranslationsSavedPayload) => void | Promise<void>
  ): Promise<boolean> {
    let dirty: TranslationDirtyState = {};
    state.update((s) => {
      dirty = s.translationsDirty;
      return s;
    });
    if (!Object.keys(dirty).length) return true;

    state.update((s) => ({ ...s, translationsSaving: true }));
    try {
      const updates: TranslationUpdates = {};
      const deletes: TranslationDelete[] = [];
      for (const change of Object.values(dirty)) {
        if (change.deleted || String(change.value ?? "") === "") {
          deletes.push({ lang: change.lang, key: change.key });
          continue;
        }
        if (!updates[change.lang]) updates[change.lang] = {};
        updates[change.lang][change.key] = change.value;
      }
      const payload: TranslationsPatchPayload = { updates, deletes };
      const res = (await api("/admin/translations", {
        method: "PATCH",
        body: JSON.stringify(payload),
      })) as TranslationsPatchResponse | AdminErrorResponse;
      if (isOkResponse(res)) {
        const result = unwrap(res);
        onToast(
          result.file_written === false
            ? at(
                "translations_file_write_warning",
                {},
                "Translations saved in DB, but JSON file was not updated"
              )
            : at("translations_saved", {}, "Translations saved")
        );
        state.update((s) => ({ ...s, translationsDirty: {} }));
        if (onTranslationsSaved) await onTranslationsSaved({ updates, deletes });
        await loadTranslations();
        return true;
      }
      if (res?.errors) {
        const summary = Object.entries(res.errors)
          .map(([key, value]) => `${key}: ${value}`)
          .join("; ");
        onToast(at("translations_validation_errors", { errors: summary }, `Errors: ${summary}`));
      } else {
        const message = adminErrorMessage(res, at);
        onToast(at("translations_save_error", { error: message }, message));
      }
      return false;
    } finally {
      state.update((s) => ({ ...s, translationsSaving: false }));
    }
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    loadTranslations,
    markDirty,
    clearDirty,
    resetField,
    addTranslationLanguage,
    saveTranslations,
  };
}
