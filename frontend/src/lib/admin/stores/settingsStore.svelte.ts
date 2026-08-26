import { adminErrorMessage } from "../errors.js";
import {
  buildAdminSettingsPath,
  unwrap,
  type ApiClient,
  type ApiResponseFor,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import { snapshotForPayload } from "./snapshotForPayload.svelte";
import { isKumaUrlValid } from "../serverStatusSettings";

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
export type PaymentMethodOrderOption = {
  id: string;
  label: string;
  provider_id: string;
  provider_label: string;
  enabled: boolean;
  admin_only: boolean;
  known: boolean;
};
export type SettingField = {
  key: string;
  label: string;
  value?: unknown;
  overridden?: boolean;
  value_source?: string | null;
  has_value?: boolean;
  secret?: boolean;
  placeholder?: string;
  description?: string;
  type?: string;
  min?: number | null;
  max?: number | null;
  choices?: SettingChoice[];
  payment_method_options?: PaymentMethodOrderOption[];
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
  /** True once the feature manifest has been loaded at least once. */
  featuresResolved: boolean;
  partnerEncryptionAvailable: boolean;
  settingsLoading: boolean;
  settingsDirty: SettingsDirtyState;
  settingsSaving: boolean;
  /** Pending changes owned by a section that writes its own contract. */
  extraDirtyCount: number;
};
type SettingsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type SettingsStore = SettingsState & {
  loadSettings: () => Promise<void>;
  /**
   * Lets a settings section that writes another contract (for example the
   * referral bonus matrix, which patches the tariff catalog) hang off the one
   * Save in the screen header instead of shipping a second Save button.
   */
  registerExtraSaver: (saver: () => void | Promise<void>) => () => void;
  reportExtraDirty: (sectionId: string, count: number) => void;
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

/** Keys the backend stored but could not apply to the running process. */
function notAppliedKeys(response: unknown): string[] {
  const value = (response as { not_applied?: unknown } | null)?.not_applied;
  return Array.isArray(value) ? value.map((key) => String(key)) : [];
}

export function createSettingsStore({ api, onToast, at }: SettingsStoreOptions): SettingsStore {
  const state = $state<SettingsStore>({
    settingsSections: [],
    features: [],
    featuresResolved: false,
    partnerEncryptionAvailable: false,
    settingsLoading: false,
    settingsDirty: {},
    settingsSaving: false,
    extraDirtyCount: 0,
    loadSettings,
    registerExtraSaver,
    reportExtraDirty,
    markDirty,
    clearDirty,
    setFieldValue,
    resetField,
    saveSettings,
  });

  // Plain collections, deliberately outside `$state`: they must not make the
  // effect that registers a saver depend on its own write.
  const extraSavers = new Set<() => void | Promise<void>>();
  const extraDirty = new Map<string, number>();

  function registerExtraSaver(saver: () => void | Promise<void>): () => void {
    extraSavers.add(saver);
    return () => {
      extraSavers.delete(saver);
    };
  }

  function reportExtraDirty(sectionId: string, count: number): void {
    if (count > 0) extraDirty.set(sectionId, count);
    else extraDirty.delete(sectionId);
    const total = [...extraDirty.values()].reduce((sum, value) => sum + value, 0);
    if (total !== state.extraDirtyCount) updateState((s) => ({ ...s, extraDirtyCount: total }));
  }

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
          featuresResolved: true,
          partnerEncryptionAvailable: Boolean(result.partner_encryption_available),
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
    const savers = [...extraSavers];
    if (!Object.keys(dirty).length && !savers.length) return true;
    if (
      Object.prototype.hasOwnProperty.call(dirty, "SERVER_STATUS_KUMA_URL") &&
      !dirty.SERVER_STATUS_KUMA_URL.deleted &&
      !isKumaUrlValid(dirty.SERVER_STATUS_KUMA_URL.value)
    ) {
      onToast(
        at(
          "settings_server_status_kuma_url_invalid",
          {},
          "Enter a valid Uptime Kuma URL using http:// or https://"
        )
      );
      return false;
    }

    updateState((s) => ({ ...s, settingsSaving: true }));
    try {
      for (const saver of savers) await saver();
      if (!Object.keys(dirty).length) return true;
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
        // A key the running process could not apply is stored but inert until
        // a restart — saying "saved" would hide exactly that.
        const notApplied = notAppliedKeys(res);
        onToast(
          notApplied.length
            ? at(
                "settings_saved_not_applied",
                { keys: notApplied.join(", ") },
                `Saved, but these settings need a restart to take effect: ${notApplied.join(", ")}`
              )
            : at("settings_saved", {}, "Settings saved")
        );
        updateState((s) => ({ ...s, settingsDirty: {} }));
        if (onSettingsSaved) await onSettingsSaved({ updates, deletes });
        await loadSettings();
        return true;
      } else if (res?.errors) {
        const summary = Object.entries(res.errors)
          .map(([k, v]) => `${k}: ${v}`)
          .join("; ");
        onToast(at("settings_validation_errors", { errors: summary }, "Errors: {errors}"));
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
