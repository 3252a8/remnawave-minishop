<script lang="ts">
  import { Input, Textarea } from "$components/ui/index.js";
  import {
    ChevronRight,
    RefreshCw,
    Trash2,
    Plus,
    Save,
    TriangleAlert,
    X,
  } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";
  import {
    AdminBadge,
    AdminButton,
    AdminEmptyState,
    AdminSelect,
  } from "$components/patterns/admin/index.js";
  import { Accordion, Switch } from "$components/ui/primitives.js";
  import { normalizeCurrencyKey } from "$lib/admin/tariffDraft.js";
  import type {
    PanelSquad,
    ProviderCurrencySupport,
    Tariff,
    TariffsCatalog,
    TariffsStore,
  } from "$lib/admin/stores/tariffsStore";
  import type {
    SettingField,
    SettingsDirtyEntry,
    SettingsSavedPayload,
    SettingsSection,
    SettingsStore,
  } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MoneyFormatter = (value: unknown, currency?: string) => string;
  type SettingsDirtyState = Record<string, SettingsDirtyEntry>;
  type SelectOption = { value: string; label: string };
  type ComponentCallback = (...args: never[]) => void;
  type ProviderKey = keyof typeof PROVIDER_FALLBACK_LABELS;
  type ProviderSupportSummary = {
    total: number;
    enabled: number;
    configured: number;
    available: number;
    blocked: number;
  };

  export let at: TranslateFn;
  export let fmtMoney: MoneyFormatter;
  export let onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void> = () => {};
  export let onOpenSettingsPath: (path: string[]) => void = () => {};

  const tariffsStore = getContext<TariffsStore>("tariffsStore");
  const settingsStore = getContext<SettingsStore>("settingsStore");

  const TRIAL_SETTING_KEYS = [
    "TRIAL_ENABLED",
    "TRIAL_DURATION_DAYS",
    "TRIAL_TRAFFIC_LIMIT_GB",
    "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
    "TRIAL_TRAFFIC_STRATEGY",
    "TRIAL_WITHOUT_TELEGRAM_ENABLED",
    "TRIAL_SQUAD_UUIDS",
    "TRIAL_PREMIUM_SQUAD_UUIDS",
  ];
  const TRIAL_SWITCH_KEYS = ["TRIAL_ENABLED", "TRIAL_WITHOUT_TELEGRAM_ENABLED"];
  const TRIAL_GENERAL_KEYS = [
    "TRIAL_DURATION_DAYS",
    "TRIAL_TRAFFIC_LIMIT_GB",
    "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
  ];
  const TRIAL_RESET_KEYS = ["TRIAL_TRAFFIC_STRATEGY"];
  const TRIAL_SQUAD_KEYS = ["TRIAL_SQUAD_UUIDS", "TRIAL_PREMIUM_SQUAD_UUIDS"];
  const REFERRAL_SETTING_KEYS = [
    "REFERRAL_WELCOME_BONUS_DAYS",
    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
    "REFERRAL_ONE_BONUS_PER_REFEREE",
    "LEGACY_REFS",
    "DISPOSABLE_EMAIL_DOMAINS",
  ];
  const REFERRAL_WELCOME_KEYS = [
    "REFERRAL_WELCOME_BONUS_DAYS",
    "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
  ];
  const REFERRAL_RULE_KEYS = [
    "REFERRAL_ONE_BONUS_PER_REFEREE",
    "LEGACY_REFS",
    "DISPOSABLE_EMAIL_DOMAINS",
  ];
  const DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER = "mailinator.com\ntemp-mail.org\nyopmail.com";
  const LEGACY_PERIODS = [
    [
      "1",
      "MONTH_1_ENABLED",
      "RUB_PRICE_1_MONTH",
      "STARS_PRICE_1_MONTH",
      "REFERRAL_BONUS_DAYS_INVITER_1_MONTH",
      "REFERRAL_BONUS_DAYS_REFEREE_1_MONTH",
    ],
    [
      "3",
      "MONTH_3_ENABLED",
      "RUB_PRICE_3_MONTHS",
      "STARS_PRICE_3_MONTHS",
      "REFERRAL_BONUS_DAYS_INVITER_3_MONTHS",
      "REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS",
    ],
    [
      "6",
      "MONTH_6_ENABLED",
      "RUB_PRICE_6_MONTHS",
      "STARS_PRICE_6_MONTHS",
      "REFERRAL_BONUS_DAYS_INVITER_6_MONTHS",
      "REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS",
    ],
    [
      "12",
      "MONTH_12_ENABLED",
      "RUB_PRICE_12_MONTHS",
      "STARS_PRICE_12_MONTHS",
      "REFERRAL_BONUS_DAYS_INVITER_12_MONTHS",
      "REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS",
    ],
  ] as const;
  const LEGACY_TARIFF_SETTING_KEYS = [
    ...LEGACY_PERIODS.flatMap((row) => row.slice(1)),
    "TRAFFIC_PACKAGES",
    "STARS_TRAFFIC_PACKAGES",
  ];
  const TRAFFIC_STRATEGY_OPTIONS = [
    { value: "NO_RESET", label: "NO_RESET" },
    { value: "DAY", label: "DAY" },
    { value: "WEEK", label: "WEEK" },
    { value: "MONTH", label: "MONTH" },
    { value: "MONTH_ROLLING", label: "MONTH_ROLLING" },
  ];
  const PROVIDER_FALLBACK_LABELS = {
    cryptopay: "CryptoPay",
    freekassa: "FreeKassa",
    heleket: "Heleket",
    lava: "LAVA",
    paykilla: "PayKilla",
    platega: "Platega",
    platega_crypto: "Platega Crypto",
    platega_sbp: "Platega SBP/card",
    severpay: "SeverPay",
    stars: "Telegram Stars",
    telegram_stars: "Telegram Stars",
    wata: "Wata",
    yookassa: "YooKassa",
  } as const;
  const PROVIDER_SETTINGS_PATHS: Partial<Record<ProviderKey, string[]>> = {
    cryptopay: ["payments", "cryptopay"],
    freekassa: ["payments", "freekassa"],
    heleket: ["payments", "heleket"],
    lava: ["payments", "lava"],
    paykilla: ["payments", "paykilla"],
    platega: ["payments", "platega"],
    platega_crypto: ["payments", "platega", "crypto"],
    platega_sbp: ["payments", "platega", "sbp"],
    severpay: ["payments", "severpay"],
    stars: ["payments", "telegram-stars"],
    telegram_stars: ["payments", "telegram-stars"],
    wata: ["payments", "wata"],
    yookassa: ["payments", "yookassa"],
  };

  let tariffsCatalog: TariffsCatalog;
  let tariffsLoading = false;
  let tariffsPath = "";
  let tariffsSaving = false;
  let panelSquads: PanelSquad[] = [];
  let providerCurrencySupport: ProviderCurrencySupport[] = [];
  let panelSquadsLoading = false;
  let settingsSections: SettingsSection[] = [];
  let settingsDirty: SettingsDirtyState = {};
  let settingsSaving = false;
  let enabledTariffs: Tariff[] = [];
  let disabledTariffs = 0;
  let settingsFieldMap = new Map<string, SettingField>();
  let trialDirtyCount = 0;
  let referralDirtyCount = 0;
  let legacyDirtyCount = 0;
  let panelSquadOptions: SelectOption[] = [];
  let catalogCurrencyKey = "rub";
  let catalogCurrencyCode = "RUB";
  let defaultCurrencyDraftKey = "rub";
  let defaultCurrencyDirty = false;
  let providerSupportSummary: ProviderSupportSummary = {
    total: 0,
    enabled: 0,
    configured: 0,
    available: 0,
    blocked: 0,
  };

  $: ({
    tariffsCatalog,
    tariffsLoading,
    tariffsPath,
    tariffsSaving,
    panelSquads,
    providerCurrencySupport,
    panelSquadsLoading,
  } = $tariffsStore);
  $: ({ settingsSections, settingsDirty, settingsSaving } = $settingsStore);

  $: enabledTariffs = (tariffsCatalog.tariffs || []).filter((tariff) => tariff.enabled !== false);
  $: disabledTariffs = Math.max(0, (tariffsCatalog.tariffs || []).length - enabledTariffs.length);
  $: settingsFieldMap = new Map(
    (settingsSections || [])
      .flatMap((section) => section.fields || [])
      .map((field) => [field.key, field])
  );
  $: trialDirtyCount = TRIAL_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length;
  $: referralDirtyCount = REFERRAL_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length;
  $: legacyDirtyCount = LEGACY_TARIFF_SETTING_KEYS.filter((key) =>
    Boolean(settingsDirty[key])
  ).length;
  $: panelSquadOptions = (panelSquads || []).map((squad) => ({
    value: squad.uuid,
    label: `${squad.name || squad.uuid} · ${String(squad.uuid || "").slice(0, 8)}...`,
  }));

  let selectedTrialSquad = "";
  let selectedTrialPremiumSquad = "";
  let trialSquadSelectKey = 0;
  let trialPremiumSquadSelectKey = 0;
  let tariffSettingsOpen: string[] = [];
  let defaultCurrencyDraft = "RUB";

  function tariffName(tariff: Tariff): string {
    return tariff?.names?.ru || tariff?.names?.en || tariff?.key || "—";
  }

  function tariffPriceSummary(tariff: Tariff): string {
    const currency = normalizeCurrencyKey(tariffsCatalog.default_currency || "rub");
    const currencyCode = currency.toUpperCase();
    if (tariff.billing_model === "traffic") {
      const packages = tariff.traffic_packages?.[currency] || [];
      const first = packages[0];
      return first
        ? `${first.gb} GB ${at("at", {}, "за")} ${fmtMoney(first.price, currencyCode)}`
        : at("tariff_traffic_packages", {}, "Пакеты трафика");
    }
    const months = [...(tariff.enabled_periods || [])];
    return months
      .map((month) => {
        const rub =
          (currency === "rub" ? tariff.prices_rub?.[String(month)] : undefined) ??
          tariff.prices?.[currency]?.[String(month)];
        const stars = tariff.prices_stars?.[String(month)];
        if (rub) return `${month} ${at("months_short", {}, "мес.")} ${fmtMoney(rub, currencyCode)}`;
        if (stars) return `${month} ${at("months_short", {}, "мес.")} ${stars} ⭐`;
        return `${month} ${at("months_short", {}, "мес.")}`;
      })
      .join(" · ");
  }

  function fieldFor(key: string, fieldMap = settingsFieldMap): SettingField {
    return fieldMap.get(key) || { key, label: key, value: "" };
  }

  function valueForKey(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): unknown {
    if (dirty[key]?.deleted) return "";
    if (Object.prototype.hasOwnProperty.call(dirty, key)) {
      return dirty[key].value;
    }
    return fieldFor(key, fieldMap).value ?? "";
  }

  function boolValue(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): boolean {
    const value = valueForKey(key, dirty, fieldMap);
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  }

  function inputValueForKey(key: string): string | number {
    const value = valueForKey(key, settingsDirty, settingsFieldMap);
    return typeof value === "string" || typeof value === "number" ? value : "";
  }

  function textValueForKey(key: string): string {
    const value = valueForKey(key, settingsDirty, settingsFieldMap);
    return value == null ? "" : String(value);
  }

  function setSetting(key: string, value: unknown): void {
    if (!settingsFieldMap.has(key)) return;
    settingsStore.markDirty(key, value);
  }

  function settingInputHandler(key: string): (event: Event) => void {
    return (event: Event) => {
      const input = event.currentTarget as HTMLInputElement | HTMLTextAreaElement | null;
      setSetting(key, input?.value ?? "");
    };
  }

  function isSettingDirty(key: string, dirty: SettingsDirtyState = settingsDirty): boolean {
    return Boolean(dirty[key]);
  }

  function dirtyCount(keys: readonly string[], dirty: SettingsDirtyState = settingsDirty): number {
    return (keys || []).filter((key) => isSettingDirty(key, dirty)).length;
  }

  function resetSetting(key: string): void {
    settingsStore.clearDirty(key);
  }

  function csvList(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): string[] {
    return String(valueForKey(key, dirty, fieldMap) || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function setCsvList(key: string, values: string[]): void {
    const normalized = Array.from(
      new Set((values || []).map((item) => String(item).trim()).filter(Boolean))
    );
    settingsStore.markDirty(key, normalized.join(","));
  }

  function addTrialSquad(uuid: string): void {
    const next = String(uuid || "").trim();
    if (!next) return;
    const current = csvList("TRIAL_SQUAD_UUIDS");
    if (!current.includes(next)) {
      setCsvList("TRIAL_SQUAD_UUIDS", [...current, next]);
    }
    selectedTrialSquad = "";
  }

  function handleTrialSquadSelect(uuid: string): void {
    addTrialSquad(uuid);
    selectedTrialSquad = "";
    trialSquadSelectKey += 1;
  }

  function addTrialPremiumSquad(uuid: string): void {
    const next = String(uuid || "").trim();
    if (!next) return;
    const current = csvList("TRIAL_PREMIUM_SQUAD_UUIDS");
    if (!current.includes(next)) {
      setCsvList("TRIAL_PREMIUM_SQUAD_UUIDS", [...current, next]);
    }
    selectedTrialPremiumSquad = "";
  }

  function handleTrialPremiumSquadSelect(uuid: string): void {
    addTrialPremiumSquad(uuid);
    selectedTrialPremiumSquad = "";
    trialPremiumSquadSelectKey += 1;
  }

  const handleTrialTrafficStrategySelect = ((value: string) =>
    setSetting("TRIAL_TRAFFIC_STRATEGY", value)) as ComponentCallback;
  const handleTrialSquadSelectChange = handleTrialSquadSelect as ComponentCallback;
  const handleTrialPremiumSquadSelectChange = handleTrialPremiumSquadSelect as ComponentCallback;

  $: catalogCurrencyKey = normalizeCurrencyKey(tariffsCatalog.default_currency || "rub");
  $: catalogCurrencyCode = catalogCurrencyKey.toUpperCase();
  $: defaultCurrencyDraft = catalogCurrencyCode;
  $: defaultCurrencyDraftKey = normalizeCurrencyKey(defaultCurrencyDraft || "rub");
  $: defaultCurrencyDirty = defaultCurrencyDraftKey !== catalogCurrencyKey;
  $: providerSupportSummary = (providerCurrencySupport || []).reduce(
    (summary, provider) => {
      const enabled = Boolean(provider.enabled);
      const configured = Boolean(provider.configured);
      const supportsDefault = Boolean(provider.supports_default_currency);
      summary.total += 1;
      if (enabled) summary.enabled += 1;
      if (enabled && configured) summary.configured += 1;
      if (enabled && configured && supportsDefault) summary.available += 1;
      if (enabled && configured && !supportsDefault) summary.blocked += 1;
      return summary;
    },
    { total: 0, enabled: 0, configured: 0, available: 0, blocked: 0 }
  );

  async function saveDefaultCurrency(): Promise<void> {
    await tariffsStore.setDefaultCurrency(defaultCurrencyDraft);
  }

  function handleDefaultCurrencyInput(event: Event): void {
    const input = event.currentTarget as HTMLInputElement | null;
    defaultCurrencyDraft = (input?.value ?? "").toUpperCase();
  }

  function handleDefaultCurrencyKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter" && defaultCurrencyDirty) void saveDefaultCurrency();
  }

  function providerCurrencyLabel(provider: ProviderCurrencySupport): string {
    if (provider.accepts_any_currency) return at("tariff_provider_any_currency", {}, "Любая");
    return (
      (provider.currencies || []).map((currency) => String(currency).toUpperCase()).join(", ") ||
      at("tariff_provider_not_declared", {}, "Не задано")
    );
  }

  function providerCurrencyVariant(
    provider: ProviderCurrencySupport
  ): "success" | "warning" | "muted" {
    if (!provider.enabled || !provider.configured) return "muted";
    return provider.supports_default_currency ? "success" : "warning";
  }

  function providerCurrencyStatus(provider: ProviderCurrencySupport): string {
    if (!provider.enabled) return at("disabled", {}, "Отключен");
    if (!provider.configured) return at("status_not_configured", {}, "Не настроен");
    if (provider.supports_default_currency) return at("tariff_currency_supported", {}, "Доступен");
    return at("tariff_currency_unsupported", {}, "Заблокирован");
  }

  function providerKey(provider: ProviderCurrencySupport): string {
    return String(provider?.id || provider?.provider_key || provider?.key || "")
      .trim()
      .toLowerCase();
  }

  function providerDisplayName(provider: ProviderCurrencySupport): string {
    const key = providerKey(provider);
    return (
      provider?.provider_label ||
      provider?.provider_name ||
      PROVIDER_FALLBACK_LABELS[key as ProviderKey] ||
      PROVIDER_FALLBACK_LABELS[
        String(provider?.provider_key || "")
          .trim()
          .toLowerCase() as ProviderKey
      ] ||
      provider?.label ||
      provider?.id ||
      "—"
    );
  }

  function providerSettingsPath(provider: ProviderCurrencySupport): string[] {
    if (Array.isArray(provider?.settings_path) && provider.settings_path.length) {
      return provider.settings_path.map((segment) => String(segment || "").trim()).filter(Boolean);
    }
    const key = providerKey(provider);
    const providerRouteKey = String(provider?.provider_key || "")
      .trim()
      .toLowerCase();
    const mapped =
      PROVIDER_SETTINGS_PATHS[key as ProviderKey] ||
      PROVIDER_SETTINGS_PATHS[providerRouteKey as ProviderKey];
    if (mapped) return mapped;
    const fallback = providerRouteKey || key;
    return fallback ? ["payments", fallback.replace(/_/g, "-")] : ["payments"];
  }

  function openProviderSettings(provider: ProviderCurrencySupport): void {
    onOpenSettingsPath(providerSettingsPath(provider));
  }

  function removeTrialSquad(uuid: string): void {
    setCsvList(
      "TRIAL_SQUAD_UUIDS",
      csvList("TRIAL_SQUAD_UUIDS").filter((item) => item !== uuid)
    );
  }

  function removeTrialPremiumSquad(uuid: string): void {
    setCsvList(
      "TRIAL_PREMIUM_SQUAD_UUIDS",
      csvList("TRIAL_PREMIUM_SQUAD_UUIDS").filter((item) => item !== uuid)
    );
  }

  function trialSquadLabel(uuid: string): string {
    return tariffsStore.squadLabel(uuid);
  }

  async function saveTariffSettings(): Promise<void> {
    await settingsStore.saveSettings(onSettingsSaved);
  }

  onMount(() => {
    void tariffsStore.loadTariffs();
    void settingsStore.loadSettings();
  });
</script>

{#if tariffsLoading}
  <AdminEmptyState>{at("loading", {}, "Загрузка…")}</AdminEmptyState>
{:else}
  <div class="admin-stat-grid">
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_total", {}, "Всего тарифов")}</span>
      <strong class="admin-stat-value">{tariffsCatalog.tariffs.length}</strong>
      <span class="admin-stat-trend"
        >{at("tariffs_stat_enabled", {}, "Включено")}: {enabledTariffs.length}</span
      >
    </div>
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_default", {}, "По умолчанию")}</span>
      <strong class="admin-stat-value">{tariffsCatalog.default_tariff || "—"}</strong>
      <span class="admin-stat-trend"
        >{at("tariffs_stat_default_hint", {}, "Используется для новых подписок")}</span
      >
    </div>
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_disabled", {}, "Отключено")}</span>
      <strong class="admin-stat-value">{disabledTariffs}</strong>
      <span class="admin-stat-trend"
        >{at("tariffs_stat_disabled_hint", {}, "Скрыто с витрины")}</span
      >
    </div>
  </div>

  <article class="admin-card admin-tariff-settings-card">
    <header class="admin-card-head">
      <div>
        <h3>{at("tariffs_trial_title", {}, "Trial access")}</h3>
        <small>
          {at(
            "tariffs_trial_subtitle",
            {},
            "Configure trial duration, traffic limit, and Remnawave squads from the tariff page."
          )}
        </small>
      </div>
      <div class="admin-editor-section-actions">
        <AdminBadge
          variant={boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)
            ? "success"
            : "muted"}
        >
          {boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)
            ? at("enabled", {}, "Enabled")
            : at("disabled", {}, "Disabled")}
        </AdminBadge>
        {#if trialDirtyCount}
          <AdminBadge variant="warning">
            {at("settings_dirty_count", { count: trialDirtyCount }, `Changes: ${trialDirtyCount}`)}
          </AdminBadge>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={saveTariffSettings}
            disabled={settingsSaving}
          >
            <Save size={13} />
            {settingsSaving ? at("btn_saving", {}, "Saving...") : at("btn_save", {}, "Save")}
          </AdminButton>
        {/if}
      </div>
    </header>
    <div class="admin-card-body admin-trial-settings-body">
      <div class="admin-settings-field-groups admin-trial-settings-groups">
        <section
          class="admin-settings-field-group"
          class:is-dirty={dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty)}
        >
          <header class="admin-settings-field-group-head">
            <div class="admin-settings-field-group-head-copy">
              <strong>{at("tariffs_trial_group_switch", {}, "Доступ")}</strong>
              <small>
                {at(
                  "tariffs_trial_group_switch_hint",
                  {},
                  "Включает или выключает выдачу пробного периода пользователям."
                )}
              </small>
            </div>
            {#if dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty)}
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty) },
                  `Изменений: ${dirtyCount(TRIAL_SWITCH_KEYS, settingsDirty)}`
                )}
              </AdminBadge>
            {/if}
          </header>
          <div class="admin-settings-field-group-body">
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_ENABLED", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_enabled", {}, "Триал включён")}
                  {#if isSettingDirty("TRIAL_ENABLED", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_ENABLED</code>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    checked={boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)}
                    onCheckedChange={(checked) => setSetting("TRIAL_ENABLED", checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                  <span
                    >{boolValue("TRIAL_ENABLED", settingsDirty, settingsFieldMap)
                      ? at("enabled", {}, "Включено")
                      : at("disabled", {}, "Выключено")}</span
                  >
                </div>
                {#if isSettingDirty("TRIAL_ENABLED", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_ENABLED")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_without_telegram_enabled", {}, "Триал без Telegram")}
                  {#if isSettingDirty("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_WITHOUT_TELEGRAM_ENABLED</code>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    checked={boolValue(
                      "TRIAL_WITHOUT_TELEGRAM_ENABLED",
                      settingsDirty,
                      settingsFieldMap
                    )}
                    onCheckedChange={(checked) =>
                      setSetting("TRIAL_WITHOUT_TELEGRAM_ENABLED", checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                  <span
                    >{boolValue("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty, settingsFieldMap)
                      ? at("enabled", {}, "Включено")
                      : at("disabled", {}, "Выключено")}</span
                  >
                </div>
                {#if isSettingDirty("TRIAL_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_WITHOUT_TELEGRAM_ENABLED")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
          </div>
        </section>

        <section
          class="admin-settings-field-group"
          class:is-dirty={dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty)}
        >
          <header class="admin-settings-field-group-head">
            <div class="admin-settings-field-group-head-copy">
              <strong>{at("tariffs_trial_group_general", {}, "Общие настройки")}</strong>
              <small>
                {at(
                  "tariffs_trial_group_general_hint",
                  {},
                  "Длительность пробного доступа и объём трафика, который получает пользователь."
                )}
              </small>
            </div>
            {#if dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty)}
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty) },
                  `Изменений: ${dirtyCount(TRIAL_GENERAL_KEYS, settingsDirty)}`
                )}
              </AdminBadge>
            {/if}
          </header>
          <div class="admin-settings-field-group-body">
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_DURATION_DAYS", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_days", {}, "Длительность, дней")}
                  {#if isSettingDirty("TRIAL_DURATION_DAYS", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_DURATION_DAYS</code>
              </div>
              <div class="admin-setting-control">
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  value={inputValueForKey("TRIAL_DURATION_DAYS")}
                  oninput={settingInputHandler("TRIAL_DURATION_DAYS")}
                />
                {#if isSettingDirty("TRIAL_DURATION_DAYS", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_DURATION_DAYS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_TRAFFIC_LIMIT_GB", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_traffic", {}, "Лимит трафика, GB")}
                  {#if isSettingDirty("TRIAL_TRAFFIC_LIMIT_GB", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_TRAFFIC_LIMIT_GB</code>
              </div>
              <div class="admin-setting-control">
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="0.1"
                  value={inputValueForKey("TRIAL_TRAFFIC_LIMIT_GB")}
                  oninput={settingInputHandler("TRIAL_TRAFFIC_LIMIT_GB")}
                />
                {#if isSettingDirty("TRIAL_TRAFFIC_LIMIT_GB", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_TRAFFIC_LIMIT_GB")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_premium_traffic", {}, "Лимит premium-трафика, GB")}
                  {#if isSettingDirty("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_PREMIUM_TRAFFIC_LIMIT_GB</code>
              </div>
              <div class="admin-setting-control">
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="0.1"
                  value={inputValueForKey("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")}
                  oninput={settingInputHandler("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")}
                />
                {#if isSettingDirty("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_PREMIUM_TRAFFIC_LIMIT_GB")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
          </div>
        </section>

        <section
          class="admin-settings-field-group"
          class:is-dirty={dirtyCount(TRIAL_RESET_KEYS, settingsDirty)}
        >
          <header class="admin-settings-field-group-head">
            <div class="admin-settings-field-group-head-copy">
              <strong>{at("tariffs_trial_group_reset", {}, "Сброс трафика")}</strong>
              <small>
                {at(
                  "tariffs_trial_group_reset_hint",
                  {},
                  "Стратегия, по которой Remnawave обновляет лимит трафика для пробного периода."
                )}
              </small>
            </div>
            {#if dirtyCount(TRIAL_RESET_KEYS, settingsDirty)}
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: dirtyCount(TRIAL_RESET_KEYS, settingsDirty) },
                  `Изменений: ${dirtyCount(TRIAL_RESET_KEYS, settingsDirty)}`
                )}
              </AdminBadge>
            {/if}
          </header>
          <div class="admin-settings-field-group-body">
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_TRAFFIC_STRATEGY", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_strategy", {}, "Стратегия сброса трафика")}
                  {#if isSettingDirty("TRIAL_TRAFFIC_STRATEGY", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_TRAFFIC_STRATEGY</code>
              </div>
              <div class="admin-setting-control">
                <AdminSelect
                  class="admin-setting-select"
                  value={String(
                    valueForKey("TRIAL_TRAFFIC_STRATEGY", settingsDirty, settingsFieldMap) ||
                      "NO_RESET"
                  )}
                  items={TRAFFIC_STRATEGY_OPTIONS}
                  ariaLabel={at("tariffs_trial_strategy", {}, "Стратегия сброса трафика")}
                  onValueChange={handleTrialTrafficStrategySelect}
                />
                {#if isSettingDirty("TRIAL_TRAFFIC_STRATEGY", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_TRAFFIC_STRATEGY")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
          </div>
        </section>

        <section
          class="admin-settings-field-group"
          class:is-dirty={dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty)}
        >
          <header class="admin-settings-field-group-head">
            <div class="admin-settings-field-group-head-copy">
              <strong>{at("tariffs_trial_group_squads", {}, "Сквады")}</strong>
              <small>
                {at(
                  "tariffs_trial_group_squads_hint",
                  {},
                  "Сквады, которые будут назначены пользователю при активации триала."
                )}
              </small>
            </div>
            {#if dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty)}
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty) },
                  `Изменений: ${dirtyCount(TRIAL_SQUAD_KEYS, settingsDirty)}`
                )}
              </AdminBadge>
            {/if}
          </header>
          <div class="admin-settings-field-group-body">
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_SQUAD_UUIDS", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_squads", {}, "Обычные Internal Squads для триала")}
                  {#if isSettingDirty("TRIAL_SQUAD_UUIDS", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_SQUAD_UUIDS</code>
                <small>
                  {at(
                    "tariffs_trial_squads_hint",
                    {},
                    "Эти сквады применяются при активации триала как обычный доступ. Если поле пустое, используются USER_SQUAD_UUIDS."
                  )}
                </small>
              </div>
              <div class="admin-setting-control admin-trial-squad-control">
                {#key trialSquadSelectKey}
                  <AdminSelect
                    value={selectedTrialSquad}
                    items={panelSquadOptions}
                    disabled={panelSquadsLoading || !panelSquadOptions.length}
                    placeholder={panelSquadsLoading
                      ? at("loading", {}, "Загрузка...")
                      : at("tariffs_trial_add_squad", {}, "Добавить сквад из панели")}
                    ariaLabel={at("tariffs_trial_add_squad", {}, "Добавить сквад из панели")}
                    onValueChange={handleTrialSquadSelectChange}
                  />
                {/key}
                {#if isSettingDirty("TRIAL_SQUAD_UUIDS", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_SQUAD_UUIDS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
                <div class="admin-chip-list">
                  {#each csvList("TRIAL_SQUAD_UUIDS", settingsDirty, settingsFieldMap) as uuid}
                    <button type="button" class="admin-chip" onclick={() => removeTrialSquad(uuid)}>
                      {trialSquadLabel(uuid)}
                      <X size={12} />
                    </button>
                  {/each}
                </div>
              </div>
            </div>
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_trial_premium_squads", {}, "Premium Internal Squads для триала")}
                  {#if isSettingDirty("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>TRIAL_PREMIUM_SQUAD_UUIDS</code>
                <small>
                  {at(
                    "tariffs_trial_premium_squads_hint",
                    {},
                    "Эти сквады добавляются к обычным сквадам триала. Если поле пустое, premium-доступ не выдаётся."
                  )}
                </small>
              </div>
              <div class="admin-setting-control admin-trial-squad-control">
                {#key trialPremiumSquadSelectKey}
                  <AdminSelect
                    value={selectedTrialPremiumSquad}
                    items={panelSquadOptions}
                    disabled={panelSquadsLoading || !panelSquadOptions.length}
                    placeholder={panelSquadsLoading
                      ? at("loading", {}, "Загрузка...")
                      : at(
                          "tariffs_trial_add_premium_squad",
                          {},
                          "Добавить premium-сквад из панели"
                        )}
                    ariaLabel={at(
                      "tariffs_trial_add_premium_squad",
                      {},
                      "Добавить premium-сквад из панели"
                    )}
                    onValueChange={handleTrialPremiumSquadSelectChange}
                  />
                {/key}
                {#if isSettingDirty("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("TRIAL_PREMIUM_SQUAD_UUIDS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
                <div class="admin-chip-list">
                  {#each csvList("TRIAL_PREMIUM_SQUAD_UUIDS", settingsDirty, settingsFieldMap) as uuid}
                    <button
                      type="button"
                      class="admin-chip"
                      onclick={() => removeTrialPremiumSquad(uuid)}
                    >
                      {trialSquadLabel(uuid)}
                      <X size={12} />
                    </button>
                  {/each}
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </article>

  <article class="admin-card admin-tariff-settings-card">
    <header class="admin-card-head">
      <div>
        <h3>{at("tariffs_referral_title", {}, "Реферальная программа")}</h3>
        <small>
          {at(
            "tariffs_referral_subtitle",
            {},
            "Настройки приветственного бонуса, правил начисления и защиты от одноразовых email."
          )}
        </small>
      </div>
      <div class="admin-editor-section-actions">
        <AdminBadge
          variant={Number(
            valueForKey("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty, settingsFieldMap) || 0
          ) > 0
            ? "success"
            : "muted"}
        >
          {Number(
            valueForKey("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty, settingsFieldMap) || 0
          ) > 0
            ? at("enabled", {}, "Включено")
            : at("disabled", {}, "Выключено")}
        </AdminBadge>
        {#if referralDirtyCount}
          <AdminBadge variant="warning">
            {at(
              "settings_dirty_count",
              { count: referralDirtyCount },
              `Изменений: ${referralDirtyCount}`
            )}
          </AdminBadge>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={saveTariffSettings}
            disabled={settingsSaving}
          >
            <Save size={13} />
            {settingsSaving
              ? at("btn_saving", {}, "Сохранение...")
              : at("btn_save", {}, "Сохранить")}
          </AdminButton>
        {/if}
      </div>
    </header>

    <div class="admin-card-body admin-trial-settings-body">
      <div class="admin-settings-field-groups admin-trial-settings-groups">
        <section
          class="admin-settings-field-group"
          class:is-dirty={dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}
        >
          <header class="admin-settings-field-group-head">
            <div class="admin-settings-field-group-head-copy">
              <strong>{at("tariffs_referral_group_welcome", {}, "Приветственный бонус")}</strong>
              <small>
                {at(
                  "tariffs_referral_group_welcome_hint",
                  {},
                  "Дни, которые получает приглашённый пользователь после регистрации по ссылке."
                )}
              </small>
            </div>
            {#if dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty) },
                  `Изменений: ${dirtyCount(REFERRAL_WELCOME_KEYS, settingsDirty)}`
                )}
              </AdminBadge>
            {/if}
          </header>
          <div class="admin-settings-field-group-body">
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_referral_welcome_bonus_days", {}, "Приветственный бонус, дней")}
                  {#if isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>REFERRAL_WELCOME_BONUS_DAYS</code>
              </div>
              <div class="admin-setting-control">
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  value={inputValueForKey("REFERRAL_WELCOME_BONUS_DAYS")}
                  oninput={settingInputHandler("REFERRAL_WELCOME_BONUS_DAYS")}
                />
                {#if isSettingDirty("REFERRAL_WELCOME_BONUS_DAYS", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("REFERRAL_WELCOME_BONUS_DAYS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>

            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty(
                "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                settingsDirty
              )}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at(
                    "tariffs_referral_without_telegram",
                    {},
                    "Начислять welcome bonus без Telegram"
                  )}
                  {#if isSettingDirty("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED</code>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    checked={boolValue(
                      "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                      settingsDirty,
                      settingsFieldMap
                    )}
                    onCheckedChange={(checked) =>
                      setSetting("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                  <span
                    >{boolValue(
                      "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
                      settingsDirty,
                      settingsFieldMap
                    )
                      ? at("enabled", {}, "Включено")
                      : at("disabled", {}, "Выключено")}</span
                  >
                </div>
                {#if isSettingDirty("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
          </div>
        </section>

        <section
          class="admin-settings-field-group"
          class:is-dirty={dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
        >
          <header class="admin-settings-field-group-head">
            <div class="admin-settings-field-group-head-copy">
              <strong>{at("tariffs_referral_group_rules", {}, "Правила и антиабьюз")}</strong>
              <small>
                {at(
                  "tariffs_referral_group_rules_hint",
                  {},
                  "Ограничения повторных бонусов и домены одноразовой почты для no-Telegram аккаунтов."
                )}
              </small>
            </div>
            {#if dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: dirtyCount(REFERRAL_RULE_KEYS, settingsDirty) },
                  `Изменений: ${dirtyCount(REFERRAL_RULE_KEYS, settingsDirty)}`
                )}
              </AdminBadge>
            {/if}
          </header>
          <div class="admin-settings-field-group-body">
            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_referral_one_bonus_per_referee", {}, "Один бонус на приглашённого")}
                  {#if isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>REFERRAL_ONE_BONUS_PER_REFEREE</code>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    checked={boolValue(
                      "REFERRAL_ONE_BONUS_PER_REFEREE",
                      settingsDirty,
                      settingsFieldMap
                    )}
                    onCheckedChange={(checked) =>
                      setSetting("REFERRAL_ONE_BONUS_PER_REFEREE", checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                  <span
                    >{boolValue("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty, settingsFieldMap)
                      ? at("enabled", {}, "Включено")
                      : at("disabled", {}, "Выключено")}</span
                  >
                </div>
                {#if isSettingDirty("REFERRAL_ONE_BONUS_PER_REFEREE", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("REFERRAL_ONE_BONUS_PER_REFEREE")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>

            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("LEGACY_REFS", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_referral_legacy_refs", {}, "Старые ref-ссылки")}
                  {#if isSettingDirty("LEGACY_REFS", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>LEGACY_REFS</code>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    checked={boolValue("LEGACY_REFS", settingsDirty, settingsFieldMap)}
                    onCheckedChange={(checked) => setSetting("LEGACY_REFS", checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                  <span
                    >{boolValue("LEGACY_REFS", settingsDirty, settingsFieldMap)
                      ? at("enabled", {}, "Включено")
                      : at("disabled", {}, "Выключено")}</span
                  >
                </div>
                {#if isSettingDirty("LEGACY_REFS", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("LEGACY_REFS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>

            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_referral_disposable_domains", {}, "Disposable email домены")}
                  {#if isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>DISPOSABLE_EMAIL_DOMAINS</code>
                <small>
                  {at(
                    "tariffs_referral_disposable_domains_hint",
                    {},
                    "По одному домену на строку или через запятую. Поддомены тоже считаются совпадением."
                  )}
                </small>
              </div>
              <div class="admin-setting-control">
                <Textarea
                  class="admin-setting-textarea"
                  rows={8}
                  placeholder={DISPOSABLE_EMAIL_DOMAINS_PLACEHOLDER}
                  value={textValueForKey("DISPOSABLE_EMAIL_DOMAINS")}
                  oninput={settingInputHandler("DISPOSABLE_EMAIL_DOMAINS")}
                />
                {#if isSettingDirty("DISPOSABLE_EMAIL_DOMAINS", settingsDirty)}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => resetSetting("DISPOSABLE_EMAIL_DOMAINS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </article>

  <div class="admin-tariff-management">
    <div class="admin-tariff-overview-grid">
      <article class="admin-card admin-tariff-currency-card">
        <header class="admin-card-head admin-tariff-panel-head">
          <div>
            <h3>{at("tariffs_currency_title", {}, "Валюта каталога")}</h3>
            <small>
              {at(
                "tariffs_currency_subtitle",
                {},
                "Цены тарифов и платёжные провайдеры проверяются по этой валюте."
              )}
            </small>
          </div>
          <AdminBadge variant="muted">{catalogCurrencyCode}</AdminBadge>
        </header>
        <div class="admin-card-body admin-tariff-currency-body">
          <div class="admin-tariff-currency-current">
            <span>{at("tariffs_currency_current", {}, "Текущая валюта")}</span>
            <strong>{catalogCurrencyCode}</strong>
          </div>
          <div class="admin-tariff-catalog-bar">
            <label class="admin-field-label-compact admin-tariff-currency-field">
              <span>{at("tariff_default_currency", {}, "Валюта оплаты")}</span>
              <Input
                class="input admin-currency-input"
                type="text"
                maxlength={12}
                value={defaultCurrencyDraft}
                oninput={handleDefaultCurrencyInput}
                onkeydown={handleDefaultCurrencyKeydown}
              />
            </label>
            {#if defaultCurrencyDirty}
              <AdminButton
                size="sm"
                variant="primary"
                onclick={saveDefaultCurrency}
                disabled={tariffsSaving}
              >
                <Save size={13} />
                {tariffsSaving
                  ? at("btn_saving", {}, "Сохранение...")
                  : at("btn_save", {}, "Сохранить")}
              </AdminButton>
            {/if}
          </div>
        </div>
      </article>

      <article class="admin-card admin-tariff-providers-card">
        <header class="admin-card-head admin-tariff-panel-head">
          <div>
            <h3>{at("tariffs_provider_title", {}, "Платёжные провайдеры")}</h3>
            <small>
              {at(
                "tariffs_provider_subtitle",
                {},
                "Здесь видно, какие провайдеры смогут принять текущую валюту каталога."
              )}
            </small>
          </div>
          <div class="admin-provider-summary">
            <AdminBadge variant="success">
              {at(
                "tariffs_provider_available_count",
                { count: providerSupportSummary.available },
                "Доступно: {count}"
              )}
            </AdminBadge>
            <AdminBadge variant="muted">
              {at(
                "tariffs_provider_enabled_count",
                { count: providerSupportSummary.enabled },
                "Включено: {count}"
              )}
            </AdminBadge>
            {#if providerSupportSummary.blocked}
              <AdminBadge variant="warning">
                {at(
                  "tariffs_provider_blocked_count",
                  { count: providerSupportSummary.blocked },
                  "Не подходят: {count}"
                )}
              </AdminBadge>
            {/if}
          </div>
        </header>
        <div class="admin-card-body">
          {#if providerCurrencySupport?.length}
            <div class="admin-provider-currency-grid">
              {#each providerCurrencySupport as provider}
                {@const providerName = providerDisplayName(provider)}
                <button
                  type="button"
                  class="admin-provider-currency"
                  class:is-supported={provider.supports_default_currency &&
                    provider.enabled &&
                    provider.configured}
                  class:is-unavailable={!provider.supports_default_currency ||
                    !provider.enabled ||
                    !provider.configured}
                  title={providerName}
                  onclick={() => openProviderSettings(provider)}
                >
                  <div class="admin-provider-currency-main">
                    <strong>{providerName}</strong>
                    <small>{providerCurrencyLabel(provider)}</small>
                  </div>
                  <AdminBadge variant={providerCurrencyVariant(provider)}>
                    {providerCurrencyStatus(provider)}
                  </AdminBadge>
                </button>
              {/each}
            </div>
          {:else}
            <AdminEmptyState>
              {at("tariffs_provider_empty", {}, "Данные по провайдерам пока не загружены.")}
            </AdminEmptyState>
          {/if}
        </div>
      </article>
    </div>

    <article class="admin-card admin-tariff-list-card">
      <header class="admin-card-head admin-tariff-list-head">
        <div>
          <h3>{at("tariffs_title", {}, "Каталог тарифов")}</h3>
          <small>
            {at("tariffs_catalog_subtitle", {}, "Периоды, цены, трафик и доступы пользователей.")}
          </small>
          <code class="admin-tariff-path">{tariffsPath || "data/tariffs.json"}</code>
        </div>
        <div class="admin-editor-section-actions">
          <AdminButton
            size="sm"
            onclick={tariffsStore.loadTariffs}
            disabled={tariffsLoading || tariffsSaving}
          >
            <RefreshCw size={13} />
            {at("btn_refresh", {}, "Обновить")}
          </AdminButton>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={tariffsStore.openCreateTariff}
            disabled={tariffsLoading || tariffsSaving}
          >
            <Plus size={13} />
            {at("btn_create_tariff", {}, "Создать тариф")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body">
        {#if !tariffsCatalog.tariffs.length}
          <AdminEmptyState>
            {at(
              "tariffs_catalog_empty",
              {},
              "Каталог пуст. Добавьте первый тариф, после сохранения будет создан JSON-файл каталога."
            )}
          </AdminEmptyState>
        {:else}
          <div class="admin-tariff-grid">
            {#each tariffsCatalog.tariffs as tariff}
              <article class="admin-tariff-card" class:is-disabled={tariff.enabled === false}>
                <div class="admin-tariff-top">
                  <div>
                    <div class="admin-tariff-title">
                      <strong>{tariffName(tariff)}</strong>
                      {#if tariff.key === tariffsCatalog.default_tariff}
                        <AdminBadge variant="success"
                          >{at("status_default", {}, "Default")}</AdminBadge
                        >
                      {/if}
                    </div>
                    <code>{tariff.key}</code>
                  </div>
                  {#if tariff.enabled === false}
                    <AdminBadge variant="muted">{at("status_disabled", {}, "Выключен")}</AdminBadge>
                  {:else}
                    <AdminBadge variant="success">{at("status_active", {}, "Активен")}</AdminBadge>
                  {/if}
                </div>
                <p>
                  {tariff.descriptions?.ru ||
                    tariff.descriptions?.en ||
                    at("no_description", {}, "Без описания")}
                </p>
                <div class="admin-tariff-facts">
                  <span
                    >{tariff.billing_model === "traffic"
                      ? at("tariff_model_traffic", {}, "Трафик")
                      : at("tariff_model_periods", {}, "Периоды")}</span
                  >
                  <span>{tariffPriceSummary(tariff)}</span>
                  <span
                    >{at("tariff_squads", {}, "Squads")}: {(tariff.squad_uuids || []).length}</span
                  >
                  <span
                    >{at("tariff_premium", {}, "Premium")}: {(tariff.premium_squad_uuids || [])
                      .length
                      ? `${tariff.premium_monthly_gb || 0} GB`
                      : "—"}</span
                  >
                  <span
                    >{at("tariff_devices", {}, "Устройства")}: {tariff.hwid_device_limit ??
                      "env"}</span
                  >
                </div>
                <div class="admin-tariff-actions">
                  <AdminButton size="sm" onclick={() => tariffsStore.openEditTariff(tariff)}>
                    {at("btn_configure", {}, "Настроить")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    onclick={() => tariffsStore.toggleTariffEnabled(tariff)}
                    disabled={tariffsSaving}
                  >
                    {tariff.enabled === false
                      ? at("btn_enable", {}, "Включить")
                      : at("btn_disable", {}, "Выключить")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    onclick={() => tariffsStore.setDefaultTariff(tariff.key)}
                    disabled={tariffsSaving ||
                      tariff.enabled === false ||
                      tariff.key === tariffsCatalog.default_tariff}
                  >
                    {at("btn_set_default", {}, "По умолчанию")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    variant="danger"
                    onclick={() =>
                      tariffsStore.updateState({
                        tariffDeleteTarget: tariff,
                        tariffDeleteOpen: true,
                      })}
                    disabled={tariffsSaving}
                    aria-label={at("btn_delete_tariff", {}, "Удалить тариф")}
                  >
                    <Trash2 size={13} />
                  </AdminButton>
                </div>
              </article>
            {/each}
          </div>
        {/if}
      </div>
    </article>
  </div>

  <Accordion.Root
    type="multiple"
    bind:value={tariffSettingsOpen}
    class="admin-accordion admin-tariff-settings-accordion"
  >
    <Accordion.Item
      value="legacy-tariffs"
      class="admin-accordion-item admin-card admin-tariff-settings-card"
    >
      <Accordion.Header class="admin-accordion-header">
        <Accordion.Trigger class="admin-accordion-trigger">
          <span class="admin-accordion-title">
            {at("tariffs_legacy_title", {}, "Совместимость с legacy-тарифами")}
          </span>
          <span class="admin-accordion-meta">
            {at(
              "tariffs_legacy_subtitle",
              {},
              "Старые периоды и пакеты трафика remnawave-tg-shop, которые используются только без JSON-каталога."
            )}{#if legacyDirtyCount}
              · {at(
                "settings_dirty_count",
                { count: legacyDirtyCount },
                `Изменений: ${legacyDirtyCount}`
              )}{/if}
          </span>
          <ChevronRight size={16} class="admin-accordion-chev" />
        </Accordion.Trigger>
      </Accordion.Header>
      <Accordion.Content class="admin-accordion-content">
        <div class="admin-card-body">
          {#if legacyDirtyCount}
            <div class="admin-editor-section-actions admin-tariff-settings-save-row">
              <AdminBadge variant="warning">
                {at(
                  "settings_dirty_count",
                  { count: legacyDirtyCount },
                  `Изменений: ${legacyDirtyCount}`
                )}
              </AdminBadge>
              <AdminButton
                size="sm"
                variant="primary"
                onclick={saveTariffSettings}
                disabled={settingsSaving}
              >
                <Save size={13} />
                {settingsSaving
                  ? at("btn_saving", {}, "Сохранение...")
                  : at("btn_save", {}, "Сохранить")}
              </AdminButton>
            </div>
          {/if}
          <div class="admin-settings-warning" role="status">
            <TriangleAlert size={16} aria-hidden="true" />
            <div class="admin-settings-warning-copy">
              <strong>{at("settings_legacy_tariffs_warning_title", {}, "Legacy tariffs")}</strong>
              <p>
                {at(
                  "settings_legacy_tariffs_warning_body",
                  {},
                  "These settings are ignored when tariffs are configured in the dedicated Tariffs section."
                )}
              </p>
            </div>
          </div>

          <div class="admin-legacy-tariff-table">
            <div class="admin-legacy-tariff-row admin-legacy-tariff-head">
              <span>{at("tariffs_legacy_period", {}, "Period")}</span>
              <span>{at("tariffs_legacy_enabled", {}, "Enabled")}</span>
              <span>{at("payment_rub", {}, "RUB")}</span>
              <span>{at("payment_stars", {}, "Stars")}</span>
              <span>{at("tariffs_legacy_ref_inviter", {}, "Inviter")}</span>
              <span>{at("tariffs_legacy_ref_referee", {}, "Friend")}</span>
            </div>
            {#each LEGACY_PERIODS as [months, enabledKey, rubKey, starsKey, inviterKey, refereeKey]}
              <div class="admin-legacy-tariff-row">
                <strong>{months} {at("months_short", {}, "mo")}</strong>
                <div class="admin-setting-switch">
                  <Switch.Root
                    checked={boolValue(enabledKey, settingsDirty, settingsFieldMap)}
                    onCheckedChange={(checked) => setSetting(enabledKey, checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                </div>
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  value={inputValueForKey(rubKey)}
                  oninput={settingInputHandler(rubKey)}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  value={inputValueForKey(starsKey)}
                  oninput={settingInputHandler(starsKey)}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  value={inputValueForKey(inviterKey)}
                  oninput={settingInputHandler(inviterKey)}
                />
                <Input
                  class="input"
                  type="number"
                  min="0"
                  step="1"
                  value={inputValueForKey(refereeKey)}
                  oninput={settingInputHandler(refereeKey)}
                />
              </div>
            {/each}
          </div>

          <div class="admin-form-row admin-form-row-2 admin-legacy-traffic-row">
            <label class="admin-field-label admin-field-label-compact">
              <span>{at("tariffs_legacy_traffic_packages", {}, "Traffic packages")}</span>
              <small>{at("tariffs_legacy_traffic_hint", {}, "Format: 10:199,50:799")}</small>
              <Input
                class="input"
                type="text"
                value={inputValueForKey("TRAFFIC_PACKAGES")}
                oninput={settingInputHandler("TRAFFIC_PACKAGES")}
              />
            </label>
            <label class="admin-field-label admin-field-label-compact">
              <span
                >{at("tariffs_legacy_stars_traffic_packages", {}, "Traffic packages, Stars")}</span
              >
              <small>{at("tariffs_legacy_traffic_hint", {}, "Format: 10:199,50:799")}</small>
              <Input
                class="input"
                type="text"
                value={inputValueForKey("STARS_TRAFFIC_PACKAGES")}
                oninput={settingInputHandler("STARS_TRAFFIC_PACKAGES")}
              />
            </label>
          </div>
        </div>
      </Accordion.Content>
    </Accordion.Item>
  </Accordion.Root>
{/if}
