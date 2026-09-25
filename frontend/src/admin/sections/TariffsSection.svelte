<script lang="ts">
  import { getSettingsStore, getTariffsStore } from "$lib/admin/context";
  import { Input, Sortable } from "$components/ui/index.js";
  import {
    ChevronRight,
    Gift,
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
  import TariffTrialSettings from "./tariffs/TariffTrialSettings.svelte";
  import { normalizeCurrencyKey } from "$lib/admin/tariffDraft";
  import {
    tariffDisplayName as tariffName,
    tariffDisplayPriceSummary,
    tariffDisplaySortKey as tariffSortKey,
    tariffGbLimit,
    tariffHwidLimit,
    tariffPremiumLimit,
  } from "$lib/admin/tariffDisplay";
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
  const tariffReconciliation = $derived(tariffsState.tariffReconciliation);
  const tariffReconciliationLoading = $derived(Boolean(tariffsState.tariffReconciliationLoading));
  const tariffReconciliationApplying = $derived(Boolean(tariffsState.tariffReconciliationApplying));
  const tariffReconciliationItems = $derived(tariffReconciliation?.items || []);
  const settingsSections: SettingsSection[] = $derived(settingsStore.settingsSections || []);
  const settingsDirty: SettingsDirtyState = $derived(settingsStore.settingsDirty || {});
  const settingsSaving = $derived(Boolean(settingsStore.settingsSaving));

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

  function handleTariffReorder(fromIndex: number, toIndex: number): void {
    void tariffsStore.moveTariff(fromIndex, toIndex);
  }

  function tariffPriceSummary(tariff: Tariff): string {
    return tariffDisplayPriceSummary(tariff, tariffsCatalog, at, fmtMoney);
  }

  function tariffUnlimitedLabel(): string {
    return at("tariff_traffic_unlimited", {}, "Unlimited");
  }

  function tariffGbLimitLabel(value: unknown): string {
    return tariffGbLimit(value, tariffUnlimitedLabel());
  }

  function tariffMonthlyTrafficLimit(tariff: Tariff): string {
    if (tariff.billing_model === "traffic") return "—";
    return tariffGbLimitLabel(tariff.monthly_gb);
  }

  function tariffPremiumTrafficLimit(tariff: Tariff): string {
    return tariffPremiumLimit(tariff, tariffUnlimitedLabel());
  }

  function tariffDeviceLimit(tariff: Tariff): string {
    return tariffHwidLimit(tariff, tariffUnlimitedLabel());
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
    if (provider.accepts_any_currency) return at("tariff_provider_any_currency", {}, "Any");
    return (
      (provider.currencies || []).map((currency) => String(currency).toUpperCase()).join(", ") ||
      at("tariff_provider_not_declared", {}, "Not declared")
    );
  }

  function providerCurrencyVariant(
    provider: ProviderCurrencySupport
  ): "success" | "warning" | "muted" {
    if (!provider.enabled || !provider.configured) return "muted";
    return provider.supports_default_currency ? "success" : "warning";
  }

  function providerCurrencyStatus(provider: ProviderCurrencySupport): string {
    if (!provider.enabled) return at("disabled", {}, "Disabled");
    if (!provider.configured) return at("status_not_configured", {}, "Not configured");
    if (provider.supports_default_currency) return at("tariff_currency_supported", {}, "Available");
    return at("tariff_currency_unsupported", {}, "Blocked");
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
  <AdminEmptyState>{at("loading", {}, "Loading…")}</AdminEmptyState>
{:else}
  <div class="admin-tariff-management">
    <article class="admin-card admin-tariff-list-card">
      <header class="admin-card-head admin-tariff-list-head">
        <div>
          <h3>{at("tariffs_title", {}, "Tariff catalog")}</h3>
          <small>
            {at("tariffs_catalog_subtitle", {}, "Periods, prices, traffic, and user access.")}
            {at(
              "tariffs_order_hint",
              {},
              "Tariffs are offered at checkout in catalog order — drag the handle to reorder."
            )}
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
            {at("btn_refresh", {}, "Refresh")}
          </AdminButton>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={tariffsStore.openCreateTariff}
            disabled={tariffsLoading || tariffsSaving}
          >
            <Plus size={13} />
            {at("btn_create_tariff", {}, "Create Tariff")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body">
        {#if !tariffsCatalog.tariffs.length}
          <AdminEmptyState>
            {at(
              "tariffs_catalog_empty",
              {},
              "The catalog is empty. Add your first tariff; a catalog JSON file will be created after saving."
            )}
          </AdminEmptyState>
        {:else}
          <Sortable
            items={tariffsCatalog.tariffs}
            class="admin-tariff-sort-row"
            getKey={tariffSortKey}
            handleLabel={at("tariff_reorder", {}, "Drag to reorder tariffs")}
            disabled={tariffsSaving}
            onReorder={handleTariffReorder}
          >
            {#snippet children(tariff: Tariff)}
              <article class="admin-tariff-card" class:is-disabled={tariff.enabled === false}>
                <div class="admin-tariff-card-main">
                  <div class="admin-tariff-title">
                    <strong>{tariffName(tariff)}</strong>
                    {#if tariff.key === tariffsCatalog.default_tariff}
                      <AdminBadge variant="success"
                        >{at("status_default", {}, "Default")}</AdminBadge
                      >
                    {/if}
                    {#if tariff.enabled === false}
                      <AdminBadge variant="muted"
                        >{at("status_disabled", {}, "Disabled")}</AdminBadge
                      >
                    {:else}
                      <AdminBadge variant="success">{at("status_active", {}, "Active")}</AdminBadge>
                    {/if}
                  </div>
                  <code>{tariff.key}</code>
                  <p>
                    {tariff.descriptions?.ru ||
                      tariff.descriptions?.en ||
                      at("no_description", {}, "No description")}
                  </p>
                </div>
                <div class="admin-tariff-facts">
                  <span
                    >{tariff.billing_model === "traffic"
                      ? at("tariff_model_traffic", {}, "Traffic")
                      : at("tariff_model_periods", {}, "Periods")}</span
                  >
                  <span>{tariffPriceSummary(tariff)}</span>
                  <span
                    >{at("tariff_squads", {}, "Squads")}: {(tariff.squad_uuids || []).length}</span
                  >
                  <span
                    >{at("tariff_regular_traffic", {}, "Standard traffic")}:
                    {tariffMonthlyTrafficLimit(tariff)}</span
                  >
                  <span
                    >{at("tariff_premium", {}, "Premium")}:
                    {tariffPremiumTrafficLimit(tariff)}</span
                  >
                  <span>{at("tariff_devices", {}, "Devices")}: {tariffDeviceLimit(tariff)}</span>
                </div>
                <div class="admin-tariff-actions">
                  <AdminButton
                    data-admin-action="open-tariff-editor"
                    size="sm"
                    onclick={() => tariffsStore.openEditTariff(tariff)}
                  >
                    {at("btn_configure", {}, "Configure")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    onclick={() => tariffsStore.toggleTariffEnabled(tariff)}
                    disabled={tariffsSaving}
                  >
                    {tariff.enabled === false
                      ? at("btn_enable", {}, "On")
                      : at("btn_disable", {}, "Off")}
                  </AdminButton>
                  <AdminButton
                    size="sm"
                    onclick={() => tariffsStore.setDefaultTariff(tariff.key)}
                    disabled={tariffsSaving ||
                      tariff.enabled === false ||
                      tariff.key === tariffsCatalog.default_tariff}
                  >
                    {at("btn_set_default", {}, "Set Default")}
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
                    aria-label={at("btn_delete_tariff", {}, "Delete Tariff")}
                  >
                    <Trash2 size={13} />
                  </AdminButton>
                </div>
              </article>
            {/snippet}
          </Sortable>
        {/if}
      </div>
    </article>

    <article class="admin-card admin-tariff-reconciliation-card">
      <header class="admin-card-head admin-tariff-panel-head">
        <div>
          <h3>{at("tariff_reconciliation_title", {}, "Subscription tariff bindings")}</h3>
          <small>
            {at(
              "tariff_reconciliation_subtitle",
              {},
              "Preview and safely repair active subscriptions that are missing a canonical tariff."
            )}
          </small>
        </div>
        <div class="admin-editor-section-actions">
          <AdminButton
            size="sm"
            onclick={tariffsStore.loadTariffReconciliation}
            disabled={tariffReconciliationLoading || tariffReconciliationApplying}
          >
            <RefreshCw size={13} />
            {at("btn_refresh", {}, "Refresh")}
          </AdminButton>
          <AdminButton
            size="sm"
            variant="primary"
            onclick={tariffsStore.applyTariffReconciliation}
            disabled={tariffReconciliationLoading ||
              tariffReconciliationApplying ||
              !tariffReconciliation?.candidates}
          >
            <Save size={13} />
            {tariffReconciliationApplying
              ? at("tariff_reconciliation_applying", {}, "Applying…")
              : at("tariff_reconciliation_apply", {}, "Apply safe matches")}
          </AdminButton>
        </div>
      </header>
      <div class="admin-card-body">
        {#if tariffReconciliationLoading && !tariffReconciliation}
          <AdminEmptyState>{at("loading", {}, "Loading…")}</AdminEmptyState>
        {:else if tariffReconciliation}
          <div class="admin-provider-summary">
            <AdminBadge variant="success">
              {at(
                "tariff_reconciliation_healthy",
                { count: tariffReconciliation.healthy },
                "Healthy: {count}"
              )}
            </AdminBadge>
            <AdminBadge variant={tariffReconciliation.candidates ? "warning" : "muted"}>
              {at(
                "tariff_reconciliation_candidates",
                { count: tariffReconciliation.candidates },
                "Safe matches: {count}"
              )}
            </AdminBadge>
            <AdminBadge variant={tariffReconciliation.unresolved ? "danger" : "muted"}>
              {at(
                "tariff_reconciliation_unresolved",
                { count: tariffReconciliation.unresolved },
                "Needs review: {count}"
              )}
            </AdminBadge>
          </div>
          {#if tariffReconciliationItems.length}
            <div class="admin-provider-currency-grid">
              {#each tariffReconciliationItems.slice(0, 20) as item (item.subscription_id)}
                <div class="admin-provider-currency">
                  <div class="admin-provider-currency-main">
                    <strong>
                      {at(
                        "tariff_reconciliation_user",
                        { user_id: item.user_minishop_id || "—" },
                        "User {user_id}"
                      )}
                    </strong>
                    <small>
                      {item.current_tariff_key || at("user_tariff_none", {}, "No tariff")}
                      →
                      {item.proposed_tariff_key ||
                        at("tariff_reconciliation_manual", {}, "manual review")}
                    </small>
                    <code>{item.reason}</code>
                  </div>
                  <AdminBadge variant={item.status === "unresolved" ? "danger" : "warning"}>
                    {item.status === "unresolved"
                      ? at("tariff_reconciliation_manual", {}, "Manual review")
                      : at("tariff_reconciliation_safe", {}, "Safe")}
                  </AdminBadge>
                </div>
              {/each}
            </div>
            {#if tariffReconciliation.items_truncated}
              <p class="admin-muted">
                <TriangleAlert size={14} />
                {at(
                  "tariff_reconciliation_truncated",
                  {},
                  "Only the first reconciliation items are shown."
                )}
              </p>
            {/if}
          {:else}
            <AdminEmptyState>
              {at(
                "tariff_reconciliation_empty",
                {},
                "All active subscriptions have canonical tariff bindings."
              )}
            </AdminEmptyState>
          {/if}
        {:else}
          <AdminEmptyState>
            {at(
              "tariff_reconciliation_unavailable",
              {},
              "Tariff binding diagnostics are unavailable."
            )}
          </AdminEmptyState>
        {/if}
      </div>
    </article>

    <article class="admin-card admin-tariff-providers-card">
      <header class="admin-card-head admin-tariff-panel-head">
        <div>
          <h3>{at("tariffs_provider_title", {}, "Payment providers")}</h3>
          <small>
            {at(
              "tariffs_provider_subtitle",
              {},
              "Shows which providers can accept the current catalog currency."
            )}
          </small>
        </div>
        <div class="admin-provider-summary">
          <AdminBadge variant="success">
            {at(
              "tariffs_provider_available_count",
              { count: providerSupportSummary.available },
              "Available: {count}"
            )}
          </AdminBadge>
          <AdminBadge variant="muted">
            {at(
              "tariffs_provider_enabled_count",
              { count: providerSupportSummary.enabled },
              "Enabled: {count}"
            )}
          </AdminBadge>
          {#if providerSupportSummary.blocked}
            <AdminBadge variant="warning">
              {at(
                "tariffs_provider_blocked_count",
                { count: providerSupportSummary.blocked },
                "Unsupported: {count}"
              )}
            </AdminBadge>
          {/if}
        </div>
      </header>
      <div class="admin-card-body admin-tariff-providers-body">
        <div class="admin-tariff-currency-bar">
          <label class="admin-tariff-currency-field">
            <span>{at("tariffs_currency_title", {}, "Catalog currency")}</span>
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
              {tariffsSaving ? at("btn_saving", {}, "Saving...") : at("btn_save", {}, "Save")}
            </AdminButton>
          {/if}
          <small class="admin-tariff-currency-hint">
            {at(
              "tariffs_currency_subtitle",
              {},
              "Tariff prices and payment providers are checked against this currency."
            )}
          </small>
        </div>
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
            {at("tariffs_provider_empty", {}, "Provider data has not been loaded yet.")}
          </AdminEmptyState>
        {/if}
      </div>
    </article>

    <TariffTrialSettings
      {at}
      {settingsDirty}
      {settingsFieldMap}
      {settingsSaving}
      {panelSquadOptions}
      {panelSquadsLoading}
      {onSettingsSaved}
    />

    <article class="admin-card tariff-referral-moved-card">
      <span class="tariff-referral-moved-icon"><Gift size={20} /></span>
      <div>
        <strong
          >{at(
            "tariffs_referral_moved_title",
            {},
            "Referral bonuses moved to Marketing programs"
          )}</strong
        >
        <small
          >{at(
            "tariffs_referral_moved_hint",
            {},
            "The tariff catalog values are unchanged. Edit the tariff × period bonus matrix in the dedicated referral settings."
          )}</small
        >
      </div>
      <AdminButton onclick={() => onOpenSettingsPath(["referral"])}>
        {at("tariffs_referral_moved_action", {}, "Configure referral bonuses")}
        <ChevronRight size={15} />
      </AdminButton>
    </article>

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
              {at("tariffs_legacy_title", {}, "Legacy tariff compatibility")}
            </span>
            <span class="admin-accordion-meta">
              {at(
                "tariffs_legacy_subtitle",
                {},
                "Old remnawave-tg-shop periods and traffic packages used only when the JSON tariff catalog is not configured."
              )}{#if legacyDirtyCount}
                · {at("settings_dirty_count", { count: legacyDirtyCount }, "Changes: {count}")}{/if}
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
                    {at("settings_dirty_count", { count: legacyDirtyCount }, "Changes: {count}")}
                  </AdminBadge>
                  <AdminButton
                    size="sm"
                    variant="primary"
                    onclick={saveTariffSettings}
                    disabled={settingsSaving}
                  >
                    <Save size={13} />
                    {settingsSaving
                      ? at("btn_saving", {}, "Saving...")
                      : at("btn_save", {}, "Save")}
                  </AdminButton>
                </div>
              {/if}
              <div class="admin-settings-warning" role="status">
                <TriangleAlert size={16} aria-hidden="true" />
                <div class="admin-settings-warning-copy">
                  <strong
                    >{at("settings_legacy_tariffs_warning_title", {}, "Legacy tariffs")}</strong
                  >
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
                    {at("tariffs_legacy_refs", {}, "Legacy ref links with user ID")}
                    {#if settingsDirty.LEGACY_REFS}
                      <AdminBadge variant="warning"
                        >{at("settings_badge_dirty", {}, "Changed")}</AdminBadge
                      >
                    {/if}
                  </strong>
                  <code>LEGACY_REFS</code>
                  <small>
                    {at(
                      "tariffs_legacy_refs_hint",
                      {},
                      "Accept links like /start ref_<telegram_id>, where the payload contains the inviter's Telegram/user ID. Keep enabled only for old shared links."
                    )}
                  </small>
                </div>
                <div class="admin-setting-control">
                  <div class="admin-setting-switch">
                    <Switch.Root
                      aria-label={at("tariffs_legacy_refs", {}, "Legacy ref links with user ID")}
                      checked={boolValue("LEGACY_REFS", settingsDirty, settingsFieldMap)}
                      onCheckedChange={(checked) => setSetting("LEGACY_REFS", checked)}
                      class="admin-switch-root"
                    >
                      <Switch.Thumb class="admin-switch-thumb" />
                    </Switch.Root>
                    <span
                      >{boolValue("LEGACY_REFS", settingsDirty, settingsFieldMap)
                        ? at("enabled", {}, "Enabled")
                        : at("disabled", {}, "Disabled")}</span
                    >
                  </div>
                  {#if settingsDirty.LEGACY_REFS}
                    <AdminButton
                      size="sm"
                      variant="ghost"
                      onclick={() => settingsStore.clearDirty("LEGACY_REFS")}
                    >
                      <X size={12} />
                      {at("reset", {}, "Reset")}
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
  </div>
{/if}

<style>
  .tariff-referral-moved-card {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    padding: 15px 16px;
  }

  .tariff-referral-moved-icon {
    width: 40px;
    height: 40px;
    display: grid;
    place-items: center;
    border-radius: 12px;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 14%, var(--admin-surface-2));
  }

  .tariff-referral-moved-card > div {
    display: grid;
    gap: 4px;
  }

  .tariff-referral-moved-card small {
    color: var(--admin-muted);
    line-height: 1.4;
  }

  @media (max-width: 680px) {
    .tariff-referral-moved-card {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .tariff-referral-moved-card :global(.admin-btn) {
      grid-column: 1 / -1;
      width: 100%;
    }
  }
</style>
