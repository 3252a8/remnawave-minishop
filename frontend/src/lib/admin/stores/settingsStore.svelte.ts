import { adminErrorMessage } from "../errors.js";
import {
  buildAdminSettingsPath,
  unwrap,
  type ApiClient,
  type ApiResponseFor,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { snapshotForPayload } from "./snapshotForPayload.svelte";

type AdminErrorResponse = {
  ok?: false;
  error?: string;
  message?: string;
  detail?: string;
  errors?: Record<string, unknown>;
};
type AdminApi = <
  Path extends Parameters<ApiClient["api"]>[0],
  Options extends RequestInit | undefined = undefined,
>(
  path: Path,
  options?: Options
) => Promise<ApiResponseFor<Path, Options> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type SettingsPatchPayload = components["schemas"]["AdminSettingsPatchBody"];

export type SettingChoice = {
  value: string;
  label: string;
  i18n_label_key?: string;
};
export type SettingWebhookHint = {
  key: string;
  path: string;
  url?: string;
  hintI18nKey?: string;
  hintFallback?: string;
};
export type SettingField = {
  key: string;
  label: string;
  value?: unknown;
  overridden?: boolean;
  has_value?: boolean;
  secret?: boolean;
  placeholder?: string;
  description?: string;
  type?: string;
  min?: number | null;
  max?: number | null;
  choices?: SettingChoice[];
  i18n_label_key?: string;
  i18n_description_key?: string;
  i18n_placeholder_key?: string;
  mutually_exclusive_key?: string;
  group?: string;
  display_group?: string;
  provider_id?: string;
  provider_info_url?: string;
  provider_label?: string;
  provider_logo_url?: string;
};
export type SettingsFieldGroup = {
  id: string;
  label?: string;
  i18nLabelKey?: string;
  fields: SettingField[];
  webhook?: SettingWebhookHint;
};
export type SettingsSection = {
  id: string;
  title?: string;
  fields: SettingField[];
};
export type SettingsDirtyEntry = {
  value: unknown;
  deleted: boolean;
};
export type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
export type SettingsUpdates = Record<string, unknown>;
export type SettingsSavedPayload = {
  updates: SettingsUpdates;
  deletes: string[];
  deferFrontendReload?: boolean;
  reloadFrontend?: boolean;
};
export type SettingsState = {
  settingsSections: SettingsSection[];
  features: string[];
  settingsLoading: boolean;
  settingsDirty: SettingsDirtyState;
  settingsSaving: boolean;
};
type SettingsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type SettingsStore = SettingsState & {
  loadSettings: () => Promise<void>;
  markDirty: (key: string, value: unknown, deleted?: boolean) => void;
  clearDirty: (key: string) => void;
  setFieldValue: (key: string, value: unknown) => void;
  resetField: (field: Pick<SettingField, "key" | "overridden">) => void;
  saveSettings: (
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>
  ) => Promise<boolean>;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

function normalizeSections(sections: unknown): SettingsSection[] {
  return Array.isArray(sections) ? (sections as SettingsSection[]) : [];
}

export function createSettingsStore({ api, onToast, at }: SettingsStoreOptions): SettingsStore {
  const state = $state<SettingsStore>({
    settingsSections: [],
    features: [],
    settingsLoading: false,
    settingsDirty: {},
    settingsSaving: false,
    loadSettings,
    markDirty,
    clearDirty,
    setFieldValue,
    resetField,
    saveSettings,
  });

  function updateState(updater: (snapshot: SettingsStore) => SettingsStore): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  async function loadSettings(): Promise<void> {
    updateState((s) => ({ ...s, settingsLoading: true, settingsDirty: {} }));
    try {
      const data = await api(buildAdminSettingsPath());
      if (isOkResponse(data)) {
        const result = unwrap(data);
        updateState((s) => ({
          ...s,
          settingsSections: normalizeSections(result.sections),
          features: Array.isArray(result.features) ? result.features : [],
        }));
      }
    } finally {
      updateState((s) => ({ ...s, settingsLoading: false }));
    }
  }

  function markDirty(key: string, value: unknown, deleted = false): void {
    updateState((s) => ({
      ...s,
      settingsDirty: { ...s.settingsDirty, [key]: { value, deleted } },
    }));
  }

  function clearDirty(key: string): void {
    updateState((s) => {
      const next = { ...s.settingsDirty };
      delete next[key];
      return { ...s, settingsDirty: next };
    });
  }

  function setFieldValue(key: string, value: unknown): void {
    updateState((s) => {
      const nextDirty = { ...s.settingsDirty };
      delete nextDirty[key];
      return {
        ...s,
        settingsDirty: nextDirty,
        settingsSections: (s.settingsSections || []).map((section) => ({
          ...section,
          fields: (section.fields || []).map((field) =>
            field.key === key ? { ...field, value, overridden: true } : field
          ),
        })),
      };
    });
  }

  async function saveSettings(
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>
  ): Promise<boolean> {
    const dirty = snapshotForPayload(state.settingsDirty);
    if (!Object.keys(dirty).length) return true;

    updateState((s) => ({ ...s, settingsSaving: true }));
    try {
      const updates: SettingsUpdates = {};
      const deletes: string[] = [];
      for (const [key, change] of Object.entries(dirty)) {
        if (change.deleted) deletes.push(key);
        else updates[key] = change.value;
      }
      const payload: SettingsPatchPayload = { updates, deletes };
      const res = await api(buildAdminSettingsPath(), {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      if (isOkResponse(res)) {
        onToast(at("settings_saved", {}, "Настройки сохранены"));
        updateState((s) => ({ ...s, settingsDirty: {} }));
        if (onSettingsSaved) await onSettingsSaved({ updates, deletes });
        await loadSettings();
        return true;
      } else if (res?.errors) {
        const summary = Object.entries(res.errors)
          .map(([k, v]) => `${k}: ${v}`)
          .join("; ");
        onToast(at("settings_validation_errors", { errors: summary }, `Ошибки: ${summary}`));
      } else {
        const message = adminErrorMessage(res, at);
        onToast(at("settings_save_error", { error: message }, message));
      }
      return false;
    } finally {
      updateState((s) => ({ ...s, settingsSaving: false }));
    }
  }

  function resetField(field: Pick<SettingField, "key" | "overridden">): void {
    if (field.overridden) {
      markDirty(field.key, "", true);
    } else {
      clearDirty(field.key);
    }
  }

  return state;
}
