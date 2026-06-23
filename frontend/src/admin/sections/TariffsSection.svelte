<script lang="ts">
  import { Input } from "$components/ui/index.js";
  import {
    ChevronRight,
    RefreshCw,
    Trash2,
    Plus,
    Save,
    TriangleAlert,
  } from "$components/ui/icons.js";
  import { getContext, onMount } from "svelte";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Accordion, Switch } from "$components/ui/primitives.js";
  import TariffReferralSettings from "./tariffs/TariffReferralSettings.svelte";
  import TariffTrialSettings from "./tariffs/TariffTrialSettings.svelte";
  import { normalizeCurrencyKey } from "$lib/admin/tariffDraft.js";
  import {
    LEGACY_PERIODS,
    LEGACY_TARIFF_SETTING_KEYS,
    boolValue as resolveBoolValue,
    inputValueForKey as resolveInputValueForKey,
    providerDisplayName,
    providerSettingsPath,
    summarizeProviderSupport,
    type ProviderSupportSummary,
    type SelectOption,
    type SettingsDirtyState,
  } from "$lib/admin/tariffSettings";
  import type {
    PanelSquad,
    ProviderCurrencySupport,
    Tariff,
    TariffsCatalog,
    TariffsStore,
  } from "$lib/admin/stores/tariffsStore";
  import type {
    SettingField,
    SettingsSavedPayload,
    SettingsSection,
    SettingsStore,
  } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MoneyFormatter = (value: unknown, currency?: string) => string;

  export let at: TranslateFn;
  export let fmtMoney: MoneyFormatter;
  export let onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void> = () => {};
  export let onOpenSettingsPath: (path: string[]) => void = () => {};

  const tariffsStore = getContext<TariffsStore>("tariffsStore");
  const settingsStore = getContext<SettingsStore>("settingsStore");

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
  $: legacyDirtyCount = LEGACY_TARIFF_SETTING_KEYS.filter((key) =>
    Boolean(settingsDirty[key])
  ).length;
  $: panelSquadOptions = (panelSquads || []).map((squad) => ({
    value: squad.uuid,
    label: `${squad.name || squad.uuid} · ${String(squad.uuid || "").slice(0, 8)}...`,
  }));

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

  function boolValue(
    key: string,
    dirty: SettingsDirtyState = settingsDirty,
    fieldMap = settingsFieldMap
  ): boolean {
    return resolveBoolValue(key, dirty, fieldMap);
  }

  function inputValueForKey(key: string): string | number {
    return resolveInputValueForKey(key, settingsDirty, settingsFieldMap);
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

  $: catalogCurrencyKey = normalizeCurrencyKey(tariffsCatalog.default_currency || "rub");
  $: catalogCurrencyCode = catalogCurrencyKey.toUpperCase();
  $: defaultCurrencyDraft = catalogCurrencyCode;
  $: defaultCurrencyDraftKey = normalizeCurrencyKey(defaultCurrencyDraft || "rub");
  $: defaultCurrencyDirty = defaultCurrencyDraftKey !== catalogCurrencyKey;
  $: providerSupportSummary = summarizeProviderSupport(providerCurrencySupport);

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

  function openProviderSettings(provider: ProviderCurrencySupport): void {
    onOpenSettingsPath(providerSettingsPath(provider));
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

  <TariffTrialSettings
    {at}
    {settingsDirty}
    {settingsFieldMap}
    {settingsSaving}
    {panelSquadOptions}
    {panelSquadsLoading}
    {onSettingsSaved}
  />

  <TariffReferralSettings
    {at}
    {settingsDirty}
    {settingsFieldMap}
    {settingsSaving}
    {onSettingsSaved}
  />

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
