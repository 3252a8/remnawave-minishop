import { adminErrorMessage } from "../errors.js";
import {
  buildAdminPanelInternalSquadsPath,
  buildAdminTariffsPath,
  unwrap,
  type ApiResponse,
  type ApiClient,
  type GetResponse,
} from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import {
  emptyTariffDraft,
  cloneCatalog,
  draftFromTariff,
  tariffFromDraft as tariffFromDraftFn,
  normalizeCurrencyKey,
  normalizeUuidList,
} from "../tariffDraft.js";
import { snapshotForPayload } from "./snapshotForPayload.svelte";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends Parameters<ApiClient["api"]>[0]>(
  path: Path,
  options?: Parameters<ApiClient["api"]>[1]
) => Promise<ApiResponse<Path> | AdminErrorResponse>;
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type TariffsResponse = GetResponse<"/api/admin/tariffs">;
type TariffsSaveResponse = Extract<ApiResponse<"/api/admin/tariffs">, { exists: boolean }>;
type TariffsSavePayload = components["schemas"]["TariffsSaveBody"];
export type Tariff = components["schemas"]["Tariff"];
export type TariffsCatalog = components["schemas"]["TariffsConfig"];
export type PanelSquad = {
  uuid: string;
  name: string;
};
export type ProviderCurrencySupport = {
  id?: string;
  key?: string;
  provider_key?: string;
  provider_label?: string;
  provider_name?: string;
  label?: string;
  enabled?: boolean;
  configured?: boolean;
  supports_default_currency?: boolean;
  accepts_any_currency?: boolean;
  currencies?: string[];
  settings_path?: string[];
};
type TariffDraftRow = Record<string, unknown>;
export type TariffDraft = ReturnType<typeof emptyTariffDraft> & Record<string, unknown>;
export type DraftSquadField = "squadUuids" | "premiumSquadUuids";
export type DraftRowsField =
  "periodRows" | "topupRows" | "premiumTopupRows" | "trafficRows" | "hwidRows";
export type TariffEditorTab = "general" | "pricing" | "topup" | "premium" | "hwid";
export type TariffsState = {
  tariffsCatalog: TariffsCatalog;
  tariffsPath: string;
  tariffsLoading: boolean;
  tariffsSaving: boolean;
  tariffEditorOpen: boolean;
  tariffEditingKey: string;
  tariffDeleteOpen: boolean;
  tariffDeleteTarget: Tariff | null;
  tariffDraft: TariffDraft;
  panelSquads: PanelSquad[];
  providerCurrencySupport: ProviderCurrencySupport[];
  panelSquadsLoading: boolean;
  selectedBaseSquad: string;
  selectedPremiumSquad: string;
  tariffEditorTab: TariffEditorTab;
};
type TariffsStoreOptions = {
  api: AdminApi;
  onTariffsSaved?: (catalog: TariffsCatalog) => void | Promise<void>;
  flash: ToastFn;
  at: TranslateFn;
};
export type TariffsStore = TariffsState & {
  updateState: (updates: Partial<TariffsState>) => void;
  loadTariffs: () => Promise<void>;
  loadPanelSquads: () => Promise<void>;
  squadLabel: (uuid: string) => string;
  addSquadToDraft: (field: DraftSquadField, uuid: string) => void;
  removeSquadFromDraft: (field: DraftSquadField, uuid: string) => void;
  openCreateTariff: () => void;
  openEditTariff: (tariff: Tariff) => void;
  saveTariffDraft: () => Promise<void>;
  toggleTariffEnabled: (tariff: Tariff) => Promise<void>;
  setDefaultTariff: (key: string) => Promise<void>;
  setDefaultCurrency: (value: string) => Promise<void>;
  deleteTariff: () => Promise<void>;
  updateDraftField: (field: string, value: unknown) => void;
  updateDraftRow: (field: DraftRowsField, index: number, updates: TariffDraftRow) => void;
  addDraftRow: (field: DraftRowsField, row: TariffDraftRow) => void;
  removeDraftRow: (field: DraftRowsField, index: number) => void;
  moveDraftRow: (field: DraftRowsField, fromIndex: number, toIndex: number) => void;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

function defaultCatalog(): TariffsCatalog {
  return {
    default_tariff: "",
    default_currency: "cny",
    topup_packages_default: { cny: [], stars: [] },
    tariffs: [],
  };
}

function normalizeCatalog(catalog: unknown): TariffsCatalog {
  return cloneCatalog(catalog || defaultCatalog()) as TariffsCatalog;
}

function normalizePanelSquads(squads: unknown): PanelSquad[] {
  return Array.isArray(squads) ? (squads as PanelSquad[]) : [];
}

function normalizeProviderCurrencySupport(value: unknown): ProviderCurrencySupport[] {
  return Array.isArray(value) ? (value as ProviderCurrencySupport[]) : [];
}

function draftValue(draft: TariffDraft, field: string): unknown {
  return (draft as Record<string, unknown>)[field];
}

function draftArray(draft: TariffDraft, field: string): unknown[] {
  const value = draftValue(draft, field);
  return Array.isArray(value) ? value : [];
}

export function createTariffsStore({
  api,
  onTariffsSaved,
  flash,
  at,
}: TariffsStoreOptions): TariffsStore {
  const state = $state<TariffsStore>({
    tariffsCatalog: {
      default_tariff: "",
      default_currency: "cny",
      topup_packages_default: { cny: [], stars: [] },
      tariffs: [],
    },
    tariffsPath: "",
    tariffsLoading: false,
    tariffsSaving: false,
    tariffEditorOpen: false,
    tariffEditingKey: "",
    tariffDeleteOpen: false,
    tariffDeleteTarget: null,
    tariffDraft: emptyTariffDraft(),
    panelSquads: [],
    providerCurrencySupport: [],
    panelSquadsLoading: false,
    selectedBaseSquad: "",
    selectedPremiumSquad: "",
    tariffEditorTab: "general",
    updateState,
    loadTariffs,
    loadPanelSquads,
    squadLabel,
    addSquadToDraft,
    removeSquadFromDraft,
    openCreateTariff,
    openEditTariff,
    saveTariffDraft,
    toggleTariffEnabled,
    setDefaultTariff,
    setDefaultCurrency,
    deleteTariff,
    updateDraftField,
    updateDraftRow,
    addDraftRow,
    removeDraftRow,
    moveDraftRow,
  });

  const tariffFromDraft = (draft: TariffDraft, defaultCurrency = "cny"): Tariff =>
    tariffFromDraftFn(draft, defaultCurrency) as Tariff;

  function updateStore(updater: (snapshot: TariffsState) => TariffsState): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  function readState(): TariffsState {
    return state;
  }

  async function loadTariffs(): Promise<void> {
    updateStore((s) => ({ ...s, tariffsLoading: true }));
    try {
      void loadPanelSquads();
      const data = (await api(buildAdminTariffsPath())) as TariffsResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        updateStore((s) => ({
          ...s,
          tariffsCatalog: normalizeCatalog(result.catalog),
          tariffsPath: result.path || "",
          providerCurrencySupport: normalizeProviderCurrencySupport(
            result.provider_currency_support
          ),
        }));
      } else {
        flash(adminErrorMessage(data, at, at("load_failed", {}, "Не удалось загрузить тарифы")));
      }
    } finally {
      updateStore((s) => ({ ...s, tariffsLoading: false }));
    }
  }

  async function loadPanelSquads(): Promise<void> {
    if (state.panelSquadsLoading) return;

    updateStore((s) => ({ ...s, panelSquadsLoading: true }));
    try {
      const data = (await api(buildAdminPanelInternalSquadsPath())) as
        GetResponse<"/api/admin/panel/internal-squads"> | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        updateStore((s) => ({ ...s, panelSquads: normalizePanelSquads(result.squads) }));
      }
    } catch (_error) {
      void _error;
      updateStore((s) => ({ ...s, panelSquads: [] }));
    } finally {
      updateStore((s) => ({ ...s, panelSquadsLoading: false }));
    }
  }

  function squadLabel(uuid: string): string {
    const squad = state.panelSquads.find((item) => item.uuid === uuid);
    return squad ? `${squad.name} · ${uuid.slice(0, 8)}…` : uuid;
  }

  function addSquadToDraft(field: DraftSquadField, uuid: string): void {
    if (!uuid) return;
    updateStore((s) => {
      const current = normalizeUuidList(draftValue(s.tariffDraft, field));
      if (current.includes(uuid)) return s;
      return { ...s, tariffDraft: { ...s.tariffDraft, [field]: [...current, uuid] } };
    });
  }

  function removeSquadFromDraft(field: DraftSquadField, uuid: string): void {
    updateStore((s) => {
      return {
        ...s,
        tariffDraft: {
          ...s.tariffDraft,
          [field]: normalizeUuidList(draftValue(s.tariffDraft, field)).filter(
            (item: string) => item !== uuid
          ),
        },
      };
    });
  }

  async function persistTariffs(nextCatalog: TariffsCatalog, successText?: string): Promise<void> {
    updateStore((s) => ({ ...s, tariffsSaving: true }));
    const currentPath = state.tariffsPath;

    try {
      const payload: TariffsSavePayload = { catalog: snapshotForPayload(nextCatalog) };
      const res = (await api(buildAdminTariffsPath(), {
        method: "PUT",
        body: JSON.stringify(payload),
      })) as TariffsSaveResponse | AdminErrorResponse;
      if (isOkResponse(res)) {
        const result = unwrap(res);
        updateStore((s) => ({
          ...s,
          tariffsCatalog: normalizeCatalog(result.catalog),
          tariffsPath: result.path || currentPath,
          providerCurrencySupport: normalizeProviderCurrencySupport(
            result.provider_currency_support || s.providerCurrencySupport || []
          ),
          tariffEditorOpen: false,
          tariffDeleteOpen: false,
          tariffDeleteTarget: null,
        }));
        if (onTariffsSaved) await onTariffsSaved(normalizeCatalog(result.catalog));
        flash(successText || at("tariffs_saved", {}, "Тарифы сохранены"));
      } else {
        flash(
          adminErrorMessage(res, at, at("tariffs_save_failed", {}, "Ошибка сохранения тарифов"))
        );
      }
    } finally {
      updateStore((s) => ({ ...s, tariffsSaving: false }));
    }
  }

  function openCreateTariff(): void {
    updateStore((s) => ({
      ...s,
      tariffEditingKey: "",
      tariffDraft: {
        ...(emptyTariffDraft() as TariffDraft),
        defaultCurrency: s.tariffsCatalog.default_currency || "cny",
      },
      tariffEditorTab: "general",
      selectedBaseSquad: "",
      selectedPremiumSquad: "",
      tariffEditorOpen: true,
    }));
  }

  function openEditTariff(tariff: Tariff): void {
    updateStore((s) => ({
      ...s,
      tariffEditingKey: tariff.key,
      tariffDraft: draftFromTariff(
        tariff,
        s.tariffsCatalog.default_currency || "cny"
      ) as TariffDraft,
      tariffEditorTab: "general",
      selectedBaseSquad: "",
      selectedPremiumSquad: "",
      tariffEditorOpen: true,
    }));
  }

  async function saveTariffDraft(): Promise<void> {
    const s = readState();
    const catalog = snapshotForPayload(s.tariffsCatalog);
    const draft = snapshotForPayload(s.tariffDraft);
    const tariff = tariffFromDraft(draft, catalog.default_currency || "cny");
    if (!tariff.key) {
      flash(at("tariff_error_key_required", {}, "Укажите ключ тарифа"));
      return;
    }
    const existing = (catalog.tariffs || []).find(
      (item) => item.key === tariff.key && item.key !== s.tariffEditingKey
    );
    if (existing) {
      flash(at("tariff_error_key_exists", {}, "Тариф с таким ключом уже есть"));
      return;
    }
    const current = catalog.tariffs || [];
    const tariffs = s.tariffEditingKey
      ? current.map((item) => (item.key === s.tariffEditingKey ? tariff : item))
      : [...current, tariff];
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash(at("tariff_error_min_enabled", {}, "Должен быть хотя бы один включённый тариф"));
      return;
    }
    const currentDefault =
      catalog.default_tariff === s.tariffEditingKey ? tariff.key : catalog.default_tariff;
    const defaultTariff = enabledKeys.includes(currentDefault) ? currentDefault : enabledKeys[0];
    await persistTariffs(
      { ...cloneCatalog(catalog), default_tariff: defaultTariff, tariffs },
      at("tariff_saved", {}, "Тариф сохранён")
    );
  }

  async function toggleTariffEnabled(tariff: Tariff): Promise<void> {
    const s = readState();
    const catalog = snapshotForPayload(s.tariffsCatalog);
    const tariffs = (catalog.tariffs || []).map((item) =>
      item.key === tariff.key ? { ...item, enabled: item.enabled === false } : item
    );
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash(at("tariff_error_min_enabled", {}, "Должен остаться хотя бы один включённый тариф"));
      return;
    }
    const defaultTariff = enabledKeys.includes(catalog.default_tariff)
      ? catalog.default_tariff
      : enabledKeys[0];
    await persistTariffs(
      { ...cloneCatalog(catalog), default_tariff: defaultTariff, tariffs },
      at("tariff_status_updated", {}, "Статус тарифа обновлён")
    );
  }

  async function setDefaultTariff(key: string): Promise<void> {
    const s = readState();
    const catalog = snapshotForPayload(s.tariffsCatalog);
    if (!key || key === catalog.default_tariff) return;
    await persistTariffs(
      { ...cloneCatalog(catalog), default_tariff: key },
      at("tariff_default_updated", {}, "Тариф по умолчанию обновлён")
    );
  }

  async function setDefaultCurrency(value: string): Promise<void> {
    const currency = normalizeCurrencyKey(value || "cny") as string;
    if (!currency || currency === "stars") {
      flash(at("tariff_currency_invalid", {}, "Укажите фиатную или криптовалюту, но не Stars"));
      return;
    }
    const s = readState();
    const catalog = snapshotForPayload(s.tariffsCatalog);
    if (currency === normalizeCurrencyKey(catalog.default_currency || "cny")) return;
    await persistTariffs(
      { ...cloneCatalog(catalog), default_currency: currency },
      at("tariff_currency_updated", {}, "Валюта оплаты обновлена")
    );
  }

  async function deleteTariff(): Promise<void> {
    const s = readState();
    const target = s.tariffDeleteTarget;
    if (!target) return;
    const catalog = snapshotForPayload(s.tariffsCatalog);
    const tariffs = (catalog.tariffs || []).filter((item) => item.key !== target.key);
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash(
        at("tariff_error_delete_last_enabled", {}, "Нельзя удалить последний включённый тариф")
      );
      return;
    }
    const defaultTariff = enabledKeys.includes(catalog.default_tariff)
      ? catalog.default_tariff
      : enabledKeys[0];
    await persistTariffs(
      { ...cloneCatalog(catalog), default_tariff: defaultTariff, tariffs },
      at("tariff_deleted", {}, "Тариф удалён")
    );
  }

  function updateDraftField(field: string, value: unknown): void {
    updateStore((s) => ({ ...s, tariffDraft: { ...s.tariffDraft, [field]: value } }));
  }

  function updateDraftRow(field: DraftRowsField, index: number, updates: TariffDraftRow): void {
    updateStore((s) => {
      const rows = [...draftArray(s.tariffDraft, field)];
      if (index < 0 || index >= rows.length) return s;
      rows[index] = { ...(rows[index] as TariffDraftRow), ...updates };
      return { ...s, tariffDraft: { ...s.tariffDraft, [field]: rows } };
    });
  }

  function addDraftRow(field: DraftRowsField, row: TariffDraftRow): void {
    updateStore((s) => ({
      ...s,
      tariffDraft: { ...s.tariffDraft, [field]: [...draftArray(s.tariffDraft, field), row] },
    }));
  }

  function removeDraftRow(field: DraftRowsField, index: number): void {
    updateStore((s) => ({
      ...s,
      tariffDraft: {
        ...s.tariffDraft,
        [field]: draftArray(s.tariffDraft, field).filter((_, idx) => idx !== index),
      },
    }));
  }

  function moveDraftRow(field: DraftRowsField, fromIndex: number, toIndex: number): void {
    updateStore((s) => {
      const rows = [...draftArray(s.tariffDraft, field)];
      if (
        fromIndex === toIndex ||
        fromIndex < 0 ||
        toIndex < 0 ||
        fromIndex >= rows.length ||
        toIndex >= rows.length
      ) {
        return s;
      }
      const [moved] = rows.splice(fromIndex, 1);
      rows.splice(toIndex, 0, moved);
      return { ...s, tariffDraft: { ...s.tariffDraft, [field]: rows } };
    });
  }

  function updateState(updates: Partial<TariffsState>): void {
    if (!Object.keys(updates).length) return;
    updateStore((s) => ({ ...s, ...updates }));
  }

  return state;
}
