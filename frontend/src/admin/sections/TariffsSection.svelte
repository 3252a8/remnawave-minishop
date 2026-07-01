<script lang="ts">
  import { getSettingsStore, getTariffsStore } from "$lib/admin/context";
  import { Input } from "$components/ui/index.js";
  import {
    ChevronRight,
    RefreshCw,
    Trash2,
    Plus,
    Save,
    TriangleAlert,
    X,
  } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import { AdminBadge, AdminButton, AdminEmptyState } from "$components/patterns/admin/index.js";
  import { Switch } from "$components/ui/primitives.js";
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
  } from "$lib/admin/stores/tariffsStore";
  import type {
    SettingField,
    SettingsSavedPayload,
    SettingsSection,
  } from "$lib/admin/stores/settingsStore";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type MoneyFormatter = (value: unknown, currency?: string) => string;

  let {
    at,
    fmtMoney,
    onSettingsSaved = () => {},
    onOpenSettingsPath = () => {},
  }: {
    at: TranslateFn;
    fmtMoney: MoneyFormatter;
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>;
    onOpenSettingsPath?: (path: string[]) => void;
  } = $props();

  const tariffsStore = getTariffsStore();
  const settingsStore = getSettingsStore();

  const tariffsState = $derived(tariffsStore);
  const tariffsCatalog: TariffsCatalog = $derived(tariffsState.tariffsCatalog);
  const tariffsLoading = $derived(Boolean(tariffsState.tariffsLoading));
  const tariffsPath = $derived(String(tariffsState.tariffsPath || ""));
  const tariffsSaving = $derived(Boolean(tariffsState.tariffsSaving));
  const panelSquads: PanelSquad[] = $derived(tariffsState.panelSquads || []);
  const providerCurrencySupport: ProviderCurrencySupport[] = $derived(
    tariffsState.providerCurrencySupport || []
  );
  const panelSquadsLoading = $derived(Boolean(tariffsState.panelSquadsLoading));
  const settingsSections: SettingsSection[] = $derived(settingsStore.settingsSections || []);
  const settingsDirty: SettingsDirtyState = $derived(settingsStore.settingsDirty || {});
  const settingsSaving = $derived(Boolean(settingsStore.settingsSaving));

  const enabledTariffs: Tariff[] = $derived(
    (tariffsCatalog.tariffs || []).filter((tariff) => tariff.enabled !== false)
  );
  const disabledTariffs = $derived(
    Math.max(0, (tariffsCatalog.tariffs || []).length - enabledTariffs.length)
  );
  const settingsFieldMap: Map<string, SettingField> = $derived(
    new Map(
      (settingsSections || [])
        .flatMap((section) => section.fields || [])
        .map((field) => [field.key, field])
    )
  );
  const legacyDirtyCount = $derived(
    LEGACY_TARIFF_SETTING_KEYS.filter((key) => Boolean(settingsDirty[key])).length
  );
  const panelSquadOptions: SelectOption[] = $derived(
    (panelSquads || []).map((squad) => ({
      value: squad.uuid,
      label: `${squad.name || squad.uuid} · ${String(squad.uuid || "").slice(0, 8)}...`,
    }))
  );

  let legacyTariffSettingsOpen = $state(false);
  let defaultCurrencyDraft = $state("RUB");

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

  function tariffUnlimitedLabel(): string {
    return at("tariff_traffic_unlimited", {}, "Безлимит");
  }

  function tariffGbLimitLabel(value: unknown): string {
    const gb = Number(value || 0);
    if (!Number.isFinite(gb) || gb <= 0) {
      return tariffUnlimitedLabel();
    }
    return `${gb} GB`;
  }

  function tariffMonthlyTrafficLimit(tariff: Tariff): string {
    if (tariff.billing_model === "traffic") return "—";
    return tariffGbLimitLabel(tariff.monthly_gb);
  }

  function tariffPremiumTrafficLimit(tariff: Tariff): string {
    if (!(tariff.premium_squad_uuids || []).length) return "—";
    return tariffGbLimitLabel(tariff.premium_monthly_gb);
  }

  function tariffDeviceLimit(tariff: Tariff): string {
    const rawLimit = tariff.hwid_device_limit;
    if (rawLimit === null || rawLimit === undefined) return "env";
    const limit = Number(rawLimit);
    if (Number.isFinite(limit) && limit === 0) {
      return tariffUnlimitedLabel();
    }
    return String(rawLimit);
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

  const catalogCurrencyKey = $derived(
    normalizeCurrencyKey(tariffsCatalog.default_currency || "rub")
  );
  const catalogCurrencyCode = $derived(catalogCurrencyKey.toUpperCase());
  const defaultCurrencyDraftKey = $derived(normalizeCurrencyKey(defaultCurrencyDraft || "rub"));
  const defaultCurrencyDirty = $derived(defaultCurrencyDraftKey !== catalogCurrencyKey);
  const providerSupportSummary: ProviderSupportSummary = $derived(
    summarizeProviderSupport(providerCurrencySupport)
  );

  $effect(() => {
    defaultCurrencyDraft = catalogCurrencyCode;
  });

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
                    >{at("tariff_regular_traffic", {}, "Обычный трафик")}:
                    {tariffMonthlyTrafficLimit(tariff)}</span
                  >
                  <span
                    >{at("tariff_premium", {}, "Premium")}:
                    {tariffPremiumTrafficLimit(tariff)}</span
                  >
                  <span>{at("tariff_devices", {}, "Устройства")}: {tariffDeviceLimit(tariff)}</span>
                </div>
                <div class="admin-tariff-actions">
                  <AdminButton
                    data-admin-action="open-tariff-editor"
                    size="sm"
                    onclick={() => tariffsStore.openEditTariff(tariff)}
                  >
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
                    data-admin-action="open-tariff-delete"
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

  <div class="admin-accordion admin-tariff-settings-accordion">
    <section class="admin-accordion-item admin-card admin-tariff-settings-card">
      <div class="admin-accordion-header">
        <button
          type="button"
          class="admin-accordion-trigger"
          data-state={legacyTariffSettingsOpen ? "open" : "closed"}
          aria-expanded={legacyTariffSettingsOpen}
          aria-controls="admin-legacy-tariff-settings"
          onclick={() => (legacyTariffSettingsOpen = !legacyTariffSettingsOpen)}
        >
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
        </button>
      </div>
      {#if legacyTariffSettingsOpen}
        <div id="admin-legacy-tariff-settings" class="admin-accordion-content" data-state="open">
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

            <div
              class="admin-setting admin-trial-setting-row"
              class:is-dirty={Boolean(settingsDirty.LEGACY_REFS)}
            >
              <div class="admin-setting-meta">
                <strong>
                  {at("tariffs_legacy_refs", {}, "Старые ref-ссылки с ID пользователя")}
                  {#if settingsDirty.LEGACY_REFS}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "Изменено")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>LEGACY_REFS</code>
                <small>
                  {at(
                    "tariffs_legacy_refs_hint",
                    {},
                    "Принимать ссылки вида /start ref_<telegram_id>, где в payload записан Telegram/user ID пригласившего. Оставляйте включённым только для старых раздач ссылок."
                  )}
                </small>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    aria-label={at(
                      "tariffs_legacy_refs",
                      {},
                      "Старые ref-ссылки с ID пользователя"
                    )}
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
                {#if settingsDirty.LEGACY_REFS}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => settingsStore.clearDirty("LEGACY_REFS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "Сбросить")}
                  </AdminButton>
                {/if}
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
                      aria-label={`${at("tariffs_legacy_enabled", {}, "Enabled")} ${months} ${at("months_short", {}, "mo")}`}
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
                  >{at(
                    "tariffs_legacy_stars_traffic_packages",
                    {},
                    "Traffic packages, Stars"
                  )}</span
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
        </div>
      {/if}
    </section>
  </div>
{/if}
