import { writable } from "svelte/store";
import {
  emptyTariffDraft,
  cloneCatalog,
  draftFromTariff,
  tariffFromDraft as tariffFromDraftFn,
  normalizeCurrencyKey,
  normalizeUuidList,
} from "../tariffDraft.js";

export function createTariffsStore({ api, onTariffsSaved, flash, at }) {
  const state = writable({
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

  const tariffFromDraft = (draft, defaultCurrency = "rub") =>
    tariffFromDraftFn(draft, defaultCurrency);

  async function loadTariffs() {
    state.update((s) => ({ ...s, tariffsLoading: true }));
    try {
      loadPanelSquads();
      const data = await api("/admin/tariffs");
      if (data?.ok) {
        state.update((s) => ({
          ...s,
          tariffsCatalog: cloneCatalog(data.catalog),
          tariffsPath: data.path || "",
          providerCurrencySupport: data.provider_currency_support || [],
        }));
      } else {
        flash(data?.message || data?.error || at("load_failed", {}, "Не удалось загрузить тарифы"));
      }
    } finally {
      state.update((s) => ({ ...s, tariffsLoading: false }));
    }
  }

  async function loadPanelSquads() {
    let loading = false;
    state.update((s) => {
      loading = s.panelSquadsLoading;
      return s;
    });
    if (loading) return;

    state.update((s) => ({ ...s, panelSquadsLoading: true }));
    try {
      const data = await api("/admin/panel/internal-squads");
      if (data?.ok) state.update((s) => ({ ...s, panelSquads: data.squads || [] }));
    } catch (_error) {
      void _error;
      state.update((s) => ({ ...s, panelSquads: [] }));
    } finally {
      state.update((s) => ({ ...s, panelSquadsLoading: false }));
    }
  }

  function squadLabel(uuid) {
    let squads = [];
    state.update((s) => {
      squads = s.panelSquads;
      return s;
    });
    const squad = squads.find((item) => item.uuid === uuid);
    return squad ? `${squad.name} · ${uuid.slice(0, 8)}…` : uuid;
  }

  function addSquadToDraft(field, uuid) {
    if (!uuid) return;
    state.update((s) => {
      const current = normalizeUuidList(s.tariffDraft[field]);
      if (current.includes(uuid)) return s;
      return { ...s, tariffDraft: { ...s.tariffDraft, [field]: [...current, uuid] } };
    });
  }

  function removeSquadFromDraft(field, uuid) {
    state.update((s) => {
      return {
        ...s,
        tariffDraft: {
          ...s.tariffDraft,
          [field]: normalizeUuidList(s.tariffDraft[field]).filter((item) => item !== uuid),
        },
      };
    });
  }

  async function persistTariffs(nextCatalog, successText) {
    state.update((s) => ({ ...s, tariffsSaving: true }));
    let currentPath = "";
    state.update((s) => {
      currentPath = s.tariffsPath;
      return s;
    });

    try {
      const res = await api("/admin/tariffs", {
        method: "PUT",
        body: JSON.stringify({ catalog: nextCatalog }),
      });
      if (res?.ok) {
        state.update((s) => ({
          ...s,
          tariffsCatalog: cloneCatalog(res.catalog),
          tariffsPath: res.path || currentPath,
          providerCurrencySupport: res.provider_currency_support || s.providerCurrencySupport || [],
          tariffEditorOpen: false,
          tariffDeleteOpen: false,
          tariffDeleteTarget: null,
        }));
        if (onTariffsSaved) await onTariffsSaved(res.catalog);
        flash(successText || at("tariffs_saved", {}, "Тарифы сохранены"));
      } else {
        flash(
          res?.message || res?.error || at("tariffs_save_failed", {}, "Ошибка сохранения тарифов")
        );
      }
    } finally {
      state.update((s) => ({ ...s, tariffsSaving: false }));
    }
  }

  function openCreateTariff() {
    state.update((s) => ({
      ...s,
      tariffEditingKey: "",
      tariffDraft: {
        ...emptyTariffDraft(),
        defaultCurrency: s.tariffsCatalog.default_currency || "rub",
      },
      tariffEditorTab: "general",
      selectedBaseSquad: "",
      selectedPremiumSquad: "",
      tariffEditorOpen: true,
    }));
  }

  function openEditTariff(tariff) {
    state.update((s) => ({
      ...s,
      tariffEditingKey: tariff.key,
      tariffDraft: draftFromTariff(tariff, s.tariffsCatalog.default_currency || "rub"),
      tariffEditorTab: "general",
      selectedBaseSquad: "",
      selectedPremiumSquad: "",
      tariffEditorOpen: true,
    }));
  }

  async function saveTariffDraft() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
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

  async function toggleTariffEnabled(tariff) {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
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

  async function setDefaultTariff(key) {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!key || key === s.tariffsCatalog.default_tariff) return;
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_tariff: key },
      at("tariff_default_updated", {}, "Тариф по умолчанию обновлён")
    );
  }

  async function setDefaultCurrency(value) {
    const currency = normalizeCurrencyKey(value || "rub");
    if (!currency || currency === "stars") {
      flash(at("tariff_currency_invalid", {}, "Укажите фиатную или криптовалюту, но не Stars"));
      return;
    }
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (currency === normalizeCurrencyKey(s.tariffsCatalog.default_currency || "rub")) return;
    await persistTariffs(
      { ...cloneCatalog(s.tariffsCatalog), default_currency: currency },
      at("tariff_currency_updated", {}, "Валюта оплаты обновлена")
    );
  }

  async function deleteTariff() {
    let s;
    state.update((st) => {
      s = st;
      return st;
    });
    if (!s.tariffDeleteTarget) return;
    const tariffs = (s.tariffsCatalog.tariffs || []).filter(
      (item) => item.key !== s.tariffDeleteTarget.key
    );
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

  function addDraftRow(field, row) {
    state.update((s) => ({
      ...s,
      tariffDraft: { ...s.tariffDraft, [field]: [...(s.tariffDraft[field] || []), row] },
    }));
  }

  function removeDraftRow(field, index) {
    state.update((s) => ({
      ...s,
      tariffDraft: {
        ...s.tariffDraft,
        [field]: (s.tariffDraft[field] || []).filter((_, idx) => idx !== index),
      },
    }));
  }

  function moveDraftRow(field, fromIndex, toIndex) {
    state.update((s) => {
      const rows = [...(s.tariffDraft[field] || [])];
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

  function updateState(updates) {
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
