import { writable } from "svelte/store";

export function createSettingsStore({ api, onToast, at }) {
  const state = writable({
    settingsSections: [],
    settingsLoading: false,
    settingsDirty: {},
    settingsSaving: false,
  });

  async function loadSettings() {
    state.update((s) => ({ ...s, settingsLoading: true, settingsDirty: {} }));
    try {
      const data = await api("/admin/settings");
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          settingsSections: data.sections || [],
        }));
      }
    } finally {
      state.update((s) => ({ ...s, settingsLoading: false }));
    }
  }

  function markDirty(key, value, deleted = false) {
    state.update((s) => ({
      ...s,
      settingsDirty: { ...s.settingsDirty, [key]: { value, deleted } },
    }));
  }

  function clearDirty(key) {
    state.update((s) => {
      const next = { ...s.settingsDirty };
      delete next[key];
      return { ...s, settingsDirty: next };
    });
  }

  async function saveSettings(onSettingsSaved) {
    let dirty = {};
    state.update((s) => {
      dirty = s.settingsDirty;
      return s;
    });
    if (!Object.keys(dirty).length) return;

    state.update((s) => ({ ...s, settingsSaving: true }));
    try {
      const updates = {};
      const deletes = [];
      for (const [key, change] of Object.entries(dirty)) {
        if (change.deleted) deletes.push(key);
        else updates[key] = change.value;
      }
      const res = await api("/admin/settings", {
        method: "PATCH",
        body: JSON.stringify({ updates, deletes }),
      });
      if (res?.ok) {
        onToast(at("settings_saved", {}, "Настройки сохранены"));
        state.update((s) => ({ ...s, settingsDirty: {} }));
        if (onSettingsSaved) await onSettingsSaved({ updates, deletes });
        await loadSettings();
      } else if (res?.errors) {
        const summary = Object.entries(res.errors)
          .map(([k, v]) => `${k}: ${v}`)
          .join("; ");
        onToast(`Ошибки: ${summary}`);
      } else {
        onToast(res?.error || "Ошибка");
      }
    } finally {
      state.update((s) => ({ ...s, settingsSaving: false }));
    }
  }

  function resetField(field) {
    if (field.overridden) {
      markDirty(field.key, "", true);
    } else {
      clearDirty(field.key);
    }
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
    loadSettings,
    markDirty,
    clearDirty,
    resetField,
    saveSettings,
  };
}
