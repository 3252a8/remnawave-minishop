import { writable, type Writable } from "svelte/store";
import { adminErrorMessage } from "../errors.js";
import { unwrap, type ApiResponse, type GetResponse } from "../../webapp/publicApi";
import type { components } from "../../api/openapi.generated";
import {
  emptyTariffDraft,
  cloneCatalog,
  draftFromTariff,
  tariffFromDraft as tariffFromDraftFn,
  normalizeCurrencyKey,
  normalizeUuidList,
} from "../tariffDraft.js";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = <Path extends string>(
  path: Path,
  options?: RequestInit
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
  | "periodRows"
  | "topupRows"
  | "premiumTopupRows"
  | "trafficRows"
  | "hwidRows";
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
export type TariffsStore = Writable<TariffsState> & {
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
    default_currency: "rub",
    topup_packages_default: { rub: [], stars: [] },
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
  const state: Writable<TariffsState> = writable({
    tariffsCatalog: {
      default_tariff: "",
      default_currency: "rub",
      topup_packages_default: { rub: [], stars: [] },
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
  });

  const tariffFromDraft = (draft: TariffDraft, defaultCurrency = "rub"): Tariff =>
    tariffFromDraftFn(draft, defaultCurrency) as Tariff;

  function readState(): TariffsState {
    let current!: TariffsState;
    state.update((s) => {
      current = s;
      return s;
    });
    return current;
  }

  async function loadTariffs(): Promise<void> {
    state.update((s) => ({ ...s, tariffsLoading: true }));
    try {
      void loadPanelSquads();
      const data = (await api("/admin/tariffs")) as TariffsResponse | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        state.update((s) => ({
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
      state.update((s) => ({ ...s, tariffsLoading: false }));
    }
  }

  async function loadPanelSquads(): Promise<void> {
    let loading = false;
    state.update((s) => {
      loading = s.panelSquadsLoading;
      return s;
    });
    if (loading) return;

    state.update((s) => ({ ...s, panelSquadsLoading: true }));
    try {
      const data = (await api("/admin/panel/internal-squads")) as
        | GetResponse<"/api/admin/panel/internal-squads">
        | AdminErrorResponse;
      if (isOkResponse(data)) {
        const result = unwrap(data);
        state.update((s) => ({ ...s, panelSquads: normalizePanelSquads(result.squads) }));
      }
    } catch (_error) {
      void _error;
      state.update((s) => ({ ...s, panelSquads: [] }));
    } finally {
      state.update((s) => ({ ...s, panelSquadsLoading: false }));
    }
  }

  function squadLabel(uuid: string): string {
    let squads: PanelSquad[] = [];
    state.update((s) => {
      squads = s.panelSquads;
      return s;
    });
    const squad = squads.find((item) => item.uuid === uuid);
    return squad ? `${squad.name} · ${uuid.slice(0, 8)}…` : uuid;
  }

  function addSquadToDraft(field: DraftSquadField, uuid: string): void {
    if (!uuid) return;
    state.update((s) => {
      const current = normalizeUuidList(draftValue(s.tariffDraft, field));
      if (current.includes(uuid)) return s;
      return { ...s, tariffDraft: { ...s.tariffDraft, [field]: [...current, uuid] } };
    });
  }

  function removeSquadFromDraft(field: DraftSquadField, uuid: string): void {
    state.update((s) => {
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
    state.update((s) => ({ ...s, tariffsSaving: true }));
    let currentPath = "";
    state.update((s) => {
      currentPath = s.tariffsPath;
      return s;
    });

    try {
      const payload: TariffsSavePayload = { catalog: nextCatalog };
      const res = (await api("/admin/tariffs", {
        method: "PUT",
        body: JSON.stringify(payload),
      })) as TariffsSaveResponse | AdminErrorResponse;
      if (isOkResponse(res)) {
        const result = unwrap(res);
        state.update((s) => ({
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
      state.update((s) => ({ ...s, tariffsSaving: false }));
    }
  }

  function openCreateTariff(): void {
    state.update((s) => ({
      ...s,
      tariffEditingKey: "",
      tariffDraft: {
        ...(emptyTariffDraft() as TariffDraft),
        defaultCurrency: s.tariffsCatalog.default_currency || "rub",
      },
      tariffEditorTab: "general",
      selectedBaseSquad: "",
      selectedPremiumSquad: "",
      tariffEditorOpen: true,
    }));
  }

  function openEditTariff(tariff: Tariff): void {
    state.update((s) => ({
      ...s,
      tariffEditingKey: tariff.key,
      tariffDraft: draftFromTariff(
        tariff,
        s.tariffsCatalog.default_currency || "rub"
      ) as TariffDraft,
      tariffEditorTab: "general",
      selectedBaseSquad: "",
      selectedPremiumSquad: "",
      tariffEditorOpen: true,
    }));
  }

  async function saveTariffDraft(): Promise<void> {
    const s = readState();
    const tariff = tariffFromDraft(s.tariffDraft, s.tariffsCatalog.default_currency || "rub");
    if (!tariff.key) {
      flash(at("tariff_error_key_required", {}, "Укажите ключ тарифа"));
      return;
    }
    const existing = (s.tariffsCatalog.tariffs || []).find(
      (item) => item.key === tariff.key && item.key !== s.tariffEditingKey
    );
    if (existing) {
      flash(at("tariff_error_key_exists", {}, "Тариф с таким ключом уже есть"));
      return;
    }
    const current = s.tariffsCatalog.tariffs || [];
    const tariffs = s.tariffEditingKey
      ? current.map((item) => (item.key === s.tariffEditingKey ? tariff : item))
      : [...current, tariff];
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash(at("tariff_error_min_enabled", {}, "Должен быть хотя бы один включённый тариф"));
      return;
    }
    const currentDefault =
      s.tariffsCatalog.default_tariff === s.tariffEditingKey
        ? tariff.key
        : s.tariffsCatalog.default_tariff;
    const defaultTariff = enabledKeys.includes(currentDefault) ? currentDefault : enabledKeys[0];
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_tariff: defaultTariff, tariffs },
      at("tariff_saved", {}, "Тариф сохранён")
    );
  }

  async function toggleTariffEnabled(tariff: Tariff): Promise<void> {
    const s = readState();
    const tariffs = (s.tariffsCatalog.tariffs || []).map((item) =>
      item.key === tariff.key ? { ...item, enabled: item.enabled === false } : item
    );
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash(at("tariff_error_min_enabled", {}, "Должен остаться хотя бы один включённый тариф"));
      return;
    }
    const defaultTariff = enabledKeys.includes(s.tariffsCatalog.default_tariff)
      ? s.tariffsCatalog.default_tariff
      : enabledKeys[0];
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_tariff: defaultTariff, tariffs },
      at("tariff_status_updated", {}, "Статус тарифа обновлён")
    );
  }

  async function setDefaultTariff(key: string): Promise<void> {
    const s = readState();
    if (!key || key === s.tariffsCatalog.default_tariff) return;
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_tariff: key },
      at("tariff_default_updated", {}, "Тариф по умолчанию обновлён")
    );
  }

  async function setDefaultCurrency(value: string): Promise<void> {
    const currency = normalizeCurrencyKey(value || "rub") as string;
    if (!currency || currency === "stars") {
      flash(at("tariff_currency_invalid", {}, "Укажите фиатную или криптовалюту, но не Stars"));
      return;
    }
    const s = readState();
    if (currency === normalizeCurrencyKey(s.tariffsCatalog.default_currency || "rub")) return;
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_currency: currency },
      at("tariff_currency_updated", {}, "Валюта оплаты обновлена")
    );
  }

  async function deleteTariff(): Promise<void> {
    const s = readState();
    const target = s.tariffDeleteTarget;
    if (!target) return;
    const tariffs = (s.tariffsCatalog.tariffs || []).filter((item) => item.key !== target.key);
    const enabledKeys = tariffs.filter((item) => item.enabled !== false).map((item) => item.key);
    if (!enabledKeys.length) {
      flash(
        at("tariff_error_delete_last_enabled", {}, "Нельзя удалить последний включённый тариф")
      );
      return;
    }
    const defaultTariff = enabledKeys.includes(s.tariffsCatalog.default_tariff)
      ? s.tariffsCatalog.default_tariff
      : enabledKeys[0];
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_tariff: defaultTariff, tariffs },
      at("tariff_deleted", {}, "Тариф удалён")
    );
  }

  function addDraftRow(field: DraftRowsField, row: TariffDraftRow): void {
    state.update((s) => ({
      ...s,
      tariffDraft: { ...s.tariffDraft, [field]: [...draftArray(s.tariffDraft, field), row] },
    }));
  }

  function removeDraftRow(field: DraftRowsField, index: number): void {
    state.update((s) => ({
      ...s,
      tariffDraft: {
        ...s.tariffDraft,
        [field]: draftArray(s.tariffDraft, field).filter((_, idx) => idx !== index),
      },
    }));
  }

  function moveDraftRow(field: DraftRowsField, fromIndex: number, toIndex: number): void {
    state.update((s) => {
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
    state.update((s) => ({ ...s, ...updates }));
  }

  return {
    subscribe: state.subscribe,
    set: state.set,
    update: state.update,
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
    addDraftRow,
    removeDraftRow,
    moveDraftRow,
  };
}
