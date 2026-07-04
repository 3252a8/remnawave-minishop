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

  const tariffs: Tariff[] = $derived(tariffsCatalog.tariffs || []);
  const enabledTariffs: Tariff[] = $derived(tariffs.filter((tariff) => tariff.enabled !== false));
  const disabledTariffs = $derived(Math.max(0, tariffs.length - enabledTariffs.length));
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
  let defaultCurrencyDraft = $state("CNY");

  function tariffName(tariff: Tariff): string {
    return (
      tariff?.names?.["zh-cn"] ||
      tariff?.names?.zh ||
      tariff?.names?.en ||
      tariff?.names?.ru ||
      tariff?.key ||
      "—"
    );
  }

  function tariffDescription(tariff: Tariff): string {
    return (
      tariff?.descriptions?.["zh-cn"] ||
      tariff?.descriptions?.zh ||
      tariff?.descriptions?.en ||
      tariff?.descriptions?.ru ||
      at("wa_tariff_no_description", {}, "暂无说明")
    );
  }

  function tariffPriceSummary(tariff: Tariff): string {
    const currency = normalizeCurrencyKey(tariffsCatalog.default_currency || "cny");
    const currencyCode = currency.toUpperCase();
    if (tariff.billing_model === "traffic") {
      const packages = tariff.traffic_packages?.[currency] || [];
      const first = packages[0];
      return first
        ? `${first.gb} GB ${at("at", {}, "每")} ${fmtMoney(first.price, currencyCode)}`
        : at("tariff_traffic_packages", {}, "流量包");
    }
    const months = [...(tariff.enabled_periods || [])];
    return months
      .map((month) => {
        const rub =
          (currency === "rub" ? tariff.prices_rub?.[String(month)] : undefined) ??
          tariff.prices?.[currency]?.[String(month)];
        const stars = tariff.prices_stars?.[String(month)];
        if (rub) return `${month} ${at("months_short", {}, "个月")} ${fmtMoney(rub, currencyCode)}`;
        if (stars) return `${month} ${at("months_short", {}, "个月")} ${stars} ⭐`;
        return `${month} ${at("months_short", {}, "个月")}`;
      })
      .join(" · ");
  }

  function tariffUnlimitedLabel(): string {
    return at("traffic_unlimited", {}, "不限流量");
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
    normalizeCurrencyKey(tariffsCatalog.default_currency || "cny")
  );
  const catalogCurrencyCode = $derived(catalogCurrencyKey.toUpperCase());
  const defaultCurrencyDraftKey = $derived(normalizeCurrencyKey(defaultCurrencyDraft || "cny"));
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
    if (provider.accepts_any_currency) return at("tariff_provider_any_currency", {}, "任意币种");
    return (
      (provider.currencies || []).map((currency) => String(currency).toUpperCase()).join(", ") ||
      at("tariff_provider_not_declared", {}, "未声明")
    );
  }

  function providerCurrencyVariant(
    provider: ProviderCurrencySupport
  ): "success" | "warning" | "muted" {
    if (!provider.enabled || !provider.configured) return "muted";
    return provider.supports_default_currency ? "success" : "warning";
  }

  function providerCurrencyStatus(provider: ProviderCurrencySupport): string {
    if (!provider.enabled) return at("disabled", {}, "已禁用");
    if (!provider.configured) return at("tariff_provider_not_declared", {}, "未声明");
    if (provider.supports_default_currency) return at("tariff_currency_supported", {}, "可用");
    return at("tariff_currency_unsupported", {}, "不支持");
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
  <AdminEmptyState>{at("loading", {}, "加载中…")}</AdminEmptyState>
{:else}
  <div class="admin-stat-grid">
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_total", {}, "套餐总数")}</span>
      <strong class="admin-stat-value">{tariffs.length}</strong>
      <span class="admin-stat-trend">{at("enabled", {}, "已启用")}: {enabledTariffs.length}</span>
    </div>
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_default", {}, "默认")}</span>
      <strong class="admin-stat-value">{tariffsCatalog.default_tariff || "—"}</strong>
      <span class="admin-stat-trend"
        >{at("tariffs_stat_default_hint", {}, "当前默认销售套餐。")}</span
      >
    </div>
    <div class="admin-stat-card">
      <span class="admin-stat-label">{at("tariffs_stat_disabled", {}, "已禁用")}</span>
      <strong class="admin-stat-value">{disabledTariffs}</strong>
      <span class="admin-stat-trend"
        >{at("tariffs_stat_disabled_hint", {}, "当前禁用的套餐数量。")}</span
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
            <h3>{at("tariffs_currency_title", {}, "套餐币种")}</h3>
            <small>
              {at("tariffs_currency_subtitle", {}, "设置套餐和支付渠道使用的币种。")}
            </small>
          </div>
          <AdminBadge variant="muted">{catalogCurrencyCode}</AdminBadge>
        </header>
        <div class="admin-card-body admin-tariff-currency-body">
          <div class="admin-tariff-currency-current">
            <span>{at("tariffs_currency_current", {}, "当前币种")}</span>
            <strong>{catalogCurrencyCode}</strong>
          </div>
          <div class="admin-tariff-catalog-bar">
            <label class="admin-field-label-compact admin-tariff-currency-field">
              <span>{at("tariff_default_currency", {}, "默认币种")}</span>
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
                  ? at("btn_syncing", {}, "同步中...")
                  : at("btn_save_tariff", {}, "保存套餐")}
              </AdminButton>
            {/if}
          </div>
        </div>
      </article>

      <article class="admin-card admin-tariff-providers-card">
        <header class="admin-card-head admin-tariff-panel-head">
          <div>
            <h3>{at("tariffs_provider_title", {}, "支付提供商")}</h3>
            <small>
              {at("tariffs_provider_subtitle", {}, "查看各支付渠道的启用状态和支持币种。")}
            </small>
          </div>
          <div class="admin-provider-summary">
            <AdminBadge variant="success">
              {at(
                "tariffs_provider_available_count",
                { count: providerSupportSummary.available },
                "可用: {count}"
              )}
            </AdminBadge>
            <AdminBadge variant="muted">
              {at(
                "tariffs_provider_enabled_count",
                { count: providerSupportSummary.enabled },
                "已启用: {count}"
              )}
            </AdminBadge>
            {#if providerSupportSummary.blocked}
              <AdminBadge variant="warning">
                {at(
                  "tariffs_provider_blocked_count",
                  { count: providerSupportSummary.blocked },
                  "不支持: {count}"
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
              {at("tariffs_provider_empty", {}, "暂未加载支付渠道数据。")}
            </AdminEmptyState>
          {/if}
        </div>
      </article>
    </div>

    <article class="admin-card admin-tariff-list-card">
      <header class="admin-card-head admin-tariff-list-head">
        <div>
          <h3>{at("tariffs_title", {}, "套餐")}</h3>
          <small>
            {at("tariffs_catalog_subtitle", {}, "销售目录、购买周期、流量包和访问权限。")}
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
            {at("btn_sync", {}, "刷新")}
          </AdminButton>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={tariffsStore.openCreateTariff}
            disabled={tariffsLoading || tariffsSaving}
          >
            <Plus size={13} />
            {at("btn_create_tariff", {}, "创建套餐")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body">
        {#if !tariffs.length}
          <AdminEmptyState>
            {at(
              "tariffs_catalog_empty",
              {},
              "目录为空，请先添加套餐；保存后将生成 JSON 套餐目录。"
            )}
          </AdminEmptyState>
        {:else}
          <div class="admin-tariff-grid">
            {#each tariffs as tariff}
              <article class="admin-tariff-card" class:is-disabled={tariff.enabled === false}>
                <div class="admin-tariff-top">
                  <div>
                    <div class="admin-tariff-title">
                      <strong>{tariffName(tariff)}</strong>
                      {#if tariff.key === tariffsCatalog.default_tariff}
                        <AdminBadge variant="success">{at("status_default", {}, "默认")}</AdminBadge
                        >
                      {/if}
                    </div>
                    <code>{tariff.key}</code>
                  </div>
                  {#if tariff.enabled === false}
                    <AdminBadge variant="muted">{at("status_disabled", {}, "已禁用")}</AdminBadge>
                  {:else}
                    <AdminBadge variant="success">{at("tariff_visible", {}, "可见")}</AdminBadge>
                  {/if}
                </div>
                <p>{tariffDescription(tariff)}</p>
                <div class="admin-tariff-facts">
                  <span
                    >{tariff.billing_model === "traffic"
                      ? at("tariff_model_traffic", {}, "流量包")
                      : at("tariff_model_periods", {}, "周期订阅")}</span
                  >
                  <span>{tariffPriceSummary(tariff)}</span>
                  <span
                    >{at("tariff_squads", {}, "套餐节点组")}: {(tariff.squad_uuids || [])
                      .length}</span
                  >
                  <span
                    >{at("tariff_regular_traffic", {}, "基础流量")}:
                    {tariffMonthlyTrafficLimit(tariff)}</span
                  >
                  <span
                    >{at("tariff_premium", {}, "高级")}:
                    {tariffPremiumTrafficLimit(tariff)}</span
                  >
                  <span>{at("tariff_devices", {}, "设备")}: {tariffDeviceLimit(tariff)}</span>
                </div>
                <div class="admin-tariff-actions">
                  <AdminButton
                    data-admin-action="open-tariff-editor"
                    size="sm"
                    onclick={() => tariffsStore.openEditTariff(tariff)}
                  >
                    {at("btn_configure", {}, "配置")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    onclick={() => tariffsStore.toggleTariffEnabled(tariff)}
                    disabled={tariffsSaving}
                  >
                    {tariff.enabled === false
                      ? at("btn_enable", {}, "开启")
                      : at("btn_disable", {}, "关闭")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    onclick={() => tariffsStore.setDefaultTariff(tariff.key)}
                    disabled={tariffsSaving ||
                      tariff.enabled === false ||
                      tariff.key === tariffsCatalog.default_tariff}
                  >
                    {at("btn_set_default", {}, "设为默认")}
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
                    aria-label={at("btn_delete_tariff", {}, "删除套餐")}
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
            {at("tariffs_legacy_title", {}, "旧版套餐兼容设置")}
          </span>
          <span class="admin-accordion-meta">
            {at(
              "tariffs_legacy_subtitle",
              {},
              "旧 remnawave-tg-shop 的周期、价格和流量包配置；仅在没有 JSON 套餐目录时使用。"
            )}{#if legacyDirtyCount}
              · {at(
                "settings_dirty_count",
                { count: legacyDirtyCount },
                `共 ${legacyDirtyCount} 处修改`
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
                    `共 ${legacyDirtyCount} 处修改`
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
                    ? at("btn_syncing", {}, "同步中...")
                    : at("btn_save_tariff", {}, "保存")}
                </AdminButton>
              </div>
            {/if}
            <div class="admin-settings-warning" role="status">
              <TriangleAlert size={16} aria-hidden="true" />
              <div class="admin-settings-warning-copy">
                <strong>{at("settings_legacy_tariffs_warning_title", {}, "旧套餐说明")}</strong>
                <p>
                  {at(
                    "settings_legacy_tariffs_warning_body",
                    {},
                    "当套餐在“套餐”区域单独配置后，这些旧兼容项不会生效。"
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
                  {at("tariffs_legacy_refs", {}, "兼容旧邀请链接")}
                  {#if settingsDirty.LEGACY_REFS}
                    <AdminBadge variant="warning"
                      >{at("settings_badge_dirty", {}, "已修改")}</AdminBadge
                    >
                  {/if}
                </strong>
                <code>LEGACY_REFS</code>
                <small>
                  {at(
                    "tariffs_legacy_refs_hint",
                    {},
                    "接受 /start ref_<telegram_id> 这种旧链接格式，其中 payload 是邀请人的 Telegram/user ID。只建议为历史推广链接保留开启。"
                  )}
                </small>
              </div>
              <div class="admin-setting-control">
                <div class="admin-setting-switch">
                  <Switch.Root
                    aria-label={at("tariffs_legacy_refs", {}, "兼容旧邀请链接")}
                    checked={boolValue("LEGACY_REFS", settingsDirty, settingsFieldMap)}
                    onCheckedChange={(checked) => setSetting("LEGACY_REFS", checked)}
                    class="admin-switch-root"
                  >
                    <Switch.Thumb class="admin-switch-thumb" />
                  </Switch.Root>
                  <span
                    >{boolValue("LEGACY_REFS", settingsDirty, settingsFieldMap)
                      ? at("enabled", {}, "已启用")
                      : at("status_disabled", {}, "已禁用")}</span
                  >
                </div>
                {#if settingsDirty.LEGACY_REFS}
                  <AdminButton
                    size="sm"
                    variant="ghost"
                    onclick={() => settingsStore.clearDirty("LEGACY_REFS")}
                  >
                    <X size={12} />
                    {at("reset", {}, "重置")}
                  </AdminButton>
                {/if}
              </div>
            </div>

            <div class="admin-legacy-tariff-table">
              <div class="admin-legacy-tariff-row admin-legacy-tariff-head">
                <span>{at("tariffs_legacy_period", {}, "周期")}</span>
                <span>{at("tariffs_legacy_enabled", {}, "已启用")}</span>
                <span>{at("payment_rub", {}, "RUB")}</span>
                <span>{at("payment_stars", {}, "Stars")}</span>
                <span>{at("tariffs_legacy_ref_inviter", {}, "邀请人奖励")}</span>
                <span>{at("tariffs_legacy_ref_referee", {}, "被邀请人奖励")}</span>
              </div>
              {#each LEGACY_PERIODS as [months, enabledKey, rubKey, starsKey, inviterKey, refereeKey]}
                <div class="admin-legacy-tariff-row">
                  <strong>{months} {at("months_short", {}, "个月")}</strong>
                  <div class="admin-setting-switch">
                    <Switch.Root
                      aria-label={`${at("tariffs_legacy_enabled", {}, "已启用")} ${months} ${at("months_short", {}, "个月")}`}
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
                <span>{at("tariffs_legacy_traffic_packages", {}, "旧版流量包")}</span>
                <small
                  >{at(
                    "tariffs_legacy_traffic_hint",
                    {},
                    "旧版流量包配置，仅在未使用 JSON 套餐目录时生效。"
                  )}</small
                >
                <Input
                  class="input"
                  type="text"
                  value={inputValueForKey("TRAFFIC_PACKAGES")}
                  oninput={settingInputHandler("TRAFFIC_PACKAGES")}
                />
              </label>
              <label class="admin-field-label admin-field-label-compact">
                <span>{at("tariffs_legacy_stars_traffic_packages", {}, "旧版 Stars 流量包")}</span>
                <small
                  >{at(
                    "tariffs_legacy_traffic_hint",
                    {},
                    "旧版流量包配置，仅在未使用 JSON 套餐目录时生效。"
                  )}</small
                >
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
