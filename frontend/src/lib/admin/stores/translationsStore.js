import { writable } from "svelte/store";

function dirtyId(lang, key) {
  return `${lang}:${key}`;
}

function normalizeLanguageCode(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, "-");
}

function isValidLanguageCode(value) {
  return /^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(value) && value.length >= 2 && value.length <= 16;
}

function languageLabel(code) {
  const labels = {
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

export function createTranslationsStore({ api, onToast, at }) {
  const state = writable({
    translationGroups: [],
    translationLanguages: [],
    translationsLoading: false,
    translationsDirty: {},
    translationsSaving: false,
    translationsPath: "",
    translationsOverrideCount: 0,
  });

  async function loadTranslations() {
    state.update((s) => ({ ...s, translationsLoading: true, translationsDirty: {} }));
    try {
      const data = await api("/admin/translations");
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          translationGroups: data.groups || [],
          translationLanguages: data.languages || [],
          translationsPath: data.path || "",
          translationsOverrideCount: data.override_count || 0,
        }));
      }
    } finally {
      state.update((s) => ({ ...s, translationsLoading: false }));
    }
  }

  function markDirty(lang, key, value, deleted = false) {
    state.update((s) => ({
      ...s,
      translationsDirty: {
        ...s.translationsDirty,
        [dirtyId(lang, key)]: { lang, key, value, deleted },
      },
    }));
  }

  function clearDirty(lang, key) {
    state.update((s) => {
      const next = { ...s.translationsDirty };
      delete next[dirtyId(lang, key)];
      return { ...s, translationsDirty: next };
    });
  }

  function resetField(lang, key, overridden) {
    if (overridden) {
      markDirty(lang, key, "", true);
    } else {
      clearDirty(lang, key);
    }
  }

  function addTranslationLanguage(rawCode) {
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

  async function saveTranslations(onTranslationsSaved) {
    let dirty = {};
    state.update((s) => {
      dirty = s.translationsDirty;
      return s;
    });
    if (!Object.keys(dirty).length) return true;

    state.update((s) => ({ ...s, translationsSaving: true }));
    try {
      const updates = {};
      const deletes = [];
      for (const change of Object.values(dirty)) {
        if (change.deleted || String(change.value ?? "") === "") {
          deletes.push({ lang: change.lang, key: change.key });
          continue;
        }
        if (!updates[change.lang]) updates[change.lang] = {};
        updates[change.lang][change.key] = change.value;
      }
      const res = await api("/admin/translations", {
        method: "PATCH",
        body: JSON.stringify({ updates, deletes }),
      });
      if (res?.ok) {
        onToast(
          res.file_written === false
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
        onToast(at("translations_save_error", { error: res?.error || "" }, res?.error || "Error"));
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
