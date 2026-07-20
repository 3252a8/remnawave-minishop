<script lang="ts">
  import { ArrowLeft, Check, ChevronsUpDown, Globe2, Menu } from "$components/ui/icons.js";
  import { onDestroy } from "svelte";
  import { MediaQuery } from "svelte/reactivity";
  import { prefersReducedMotion } from "svelte/motion";
  import { fade } from "svelte/transition";
  import { Select } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";
  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import AdminHeaderActions from "./AdminHeaderActions.svelte";
  import AdminLazyModals from "./AdminLazyModals.svelte";
  import ConfigAlertsBanner from "./ConfigAlertsBanner.svelte";
  import { dynamicComponent, type DynamicComponent } from "./adminLazyComponents";
  import type { AdminSectionDescriptor } from "./sections/registry";
  import type { SettingsSavedPayload } from "$lib/admin/stores/settingsStore";
  import type { TranslationsSavedPayload } from "$lib/admin/stores/translationsStore";
  import type { AdminUser } from "$lib/admin/stores/usersStore";
  import type { UsersFilter, UsersRouteFilters } from "$lib/admin/usersRouteFilters";

  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type SettingsPath = string[];
  type LanguageOption = { value: string; label: string; flag?: string };
  type LanguageChangeMeta = { section: "admin"; adminSection: string };
  type SectionMeta = { title: string; subtitle: string };
  type NavGroup = {
    id: string;
    order: number;
    label: string;
    items: Array<AdminSectionDescriptor & { label: string }>;
  };
  type DateFormatter = (value: unknown) => string;
  type MoneyFormatter = (value: unknown, currency?: string | null) => string;
  type BadgeVariant = "success" | "danger" | "warning" | "muted";
  type SupportStoreBridge = { stats?: { total_unread_admin?: number | null } | null };
  type LogsStoreBridge = { logsTotal?: number | null };
  type AdsStoreBridge = { setCreateOpen: (open: boolean) => void };
  type PromosStoreBridge = { setCreateOpen: (open: boolean) => void };
  type TariffsStoreBridge = { openCreateTariff: () => void };
  type SettingsStoreBridge = {
    saveSettings: (callback: (payload: SettingsSavedPayload) => void | Promise<void>) => unknown;
  };
  type TranslationsStoreBridge = {
    saveTranslations: (
      callback: (payload: TranslationsSavedPayload) => void | Promise<void>
    ) => unknown;
  };
  type StatsStoreBridge = { triggerSync: () => unknown };

  let {
    active,
    activeSectionComponent,
    activeSectionLoading,
    availableFeatures,
    adsStore,
    appFaviconUrl,
    appFaviconUseCustom,
    appRepositoryUrl,
    appVersion,
    at,
    brand,
    brandTitle,
    currentLang,
    dirtyCount,
    fmtDate,
    fmtDateShort,
    fmtMoney,
    featureAvailable,
    initialTicketId,
    languageBusy,
    languageOptions,
    logsStore,
    meta,
    NAV_GROUPS,
    onClose,
    onCloseUser,
    onExportPayments,
    onLanguageChange,
    onOpenPaymentUserCard,
    onOpenSettingsPath,
    onOpenUserCard,
    onOpenUsersFilter,
    onUsersFiltersChange,
    onSaveSettings,
    onSaveTranslations,
    onSetActive,
    onSettingsPathChange,
    openTelegramProfileLink,
    paymentStatusVariant,
    panelStatusBadge,
    promosStore,
    resolvedAvatarUrl,
    routePrefix,
    settingsPath,
    settingsSaving,
    settingsStore,
    sidebarOpen = $bindable(false),
    statsStore,
    supportStore,
    syncBusy,
    tariffsStore,
    translationsDirtyCount,
    translationsSaving,
    translationsStore,
    trafficLeftLabel,
    trafficOfLabel,
    trafficPercentValue,
    userDisplayName,
    userInitials,
    userSecondaryName,
    userTelegramProfileLink,
    userTelegramProfileLinkKind,
    warmSectionComponent,
    t,
  }: {
    active: string;
    activeSectionComponent: DynamicComponent | null;
    activeSectionLoading: boolean;
    availableFeatures: readonly string[];
    adsStore: AdsStoreBridge;
    appFaviconUrl: string;
    appFaviconUseCustom: boolean;
    appRepositoryUrl: string;
    appVersion: string;
    at: TranslateFn;
    brand: Record<string, unknown>;
    brandTitle: string;
    currentLang: string;
    dirtyCount: number;
    fmtDate: DateFormatter;
    fmtDateShort: DateFormatter;
    fmtMoney: MoneyFormatter;
    featureAvailable: boolean;
    initialTicketId: number | null;
    languageBusy: boolean;
    languageOptions: LanguageOption[];
    logsStore: LogsStoreBridge;
    meta: SectionMeta;
    NAV_GROUPS: NavGroup[];
    onClose: () => void;
    onCloseUser: () => void;
    onExportPayments: () => void;
    onLanguageChange: (value: string, meta: LanguageChangeMeta) => void;
    onOpenPaymentUserCard: (userId: unknown) => void;
    onOpenSettingsPath: (path?: unknown) => void;
    onOpenUserCard: (userId: unknown) => void;
    onOpenUsersFilter: (filter: UsersFilter) => void;
    onUsersFiltersChange: (filters: UsersRouteFilters) => void;
    onSaveSettings: (payload: SettingsSavedPayload) => void | Promise<void>;
    onSaveTranslations: (payload: TranslationsSavedPayload) => void | Promise<void>;
    onSetActive: (id: string) => void;
    onSettingsPathChange: (path: SettingsPath) => void;
    openTelegramProfileLink: (url: string) => boolean;
    paymentStatusVariant: (status: unknown) => BadgeVariant;
    panelStatusBadge: (user: AdminUser | null | undefined) => {
      label: string;
      variant: BadgeVariant;
    };
    promosStore: PromosStoreBridge;
    resolvedAvatarUrl: (user: AdminUser | null | undefined) => string;
    routePrefix: string;
    settingsPath: SettingsPath;
    settingsSaving: boolean;
    settingsStore: SettingsStoreBridge;
    sidebarOpen: boolean;
    statsStore: StatsStoreBridge;
    supportStore: SupportStoreBridge;
    syncBusy: boolean;
    tariffsStore: TariffsStoreBridge;
    translationsDirtyCount: number;
    translationsSaving: boolean;
    translationsStore: TranslationsStoreBridge;
    trafficLeftLabel: (used: unknown, limit: unknown) => string;
    trafficOfLabel: (used: unknown, limit: unknown) => string;
    trafficPercentValue: (left: unknown, total: unknown) => number;
    userDisplayName: (user: AdminUser | null | undefined) => string;
    userInitials: (user: AdminUser | null | undefined) => string;
    userSecondaryName: (user: AdminUser | null | undefined) => string;
    userTelegramProfileLink: (user: AdminUser | null | undefined) => string;
    userTelegramProfileLinkKind: (user: AdminUser | null | undefined) => string;
    warmSectionComponent: (section: AdminSectionDescriptor) => void;
    t: TranslateFn;
  } = $props();

  const compactQuery = new MediaQuery("max-width: 720px", false);
  const isCompact = $derived(compactQuery.current);
  let adminLanguageMenuOpen = $state(false);
  let adminLanguageClickGuard = $state(false);
  let adminLanguageClickGuardArmed = $state(false);
  let adminLanguageClickGuardTimer: ReturnType<typeof window.setTimeout> | null = null;
  let adminLanguageClickGuardArmTimer: ReturnType<typeof window.setTimeout> | null = null;
  const adminLanguageGuardActive = $derived(
    isCompact && (adminLanguageMenuOpen || adminLanguageClickGuard)
  );
  const currentLanguageOption = $derived(
    languageOptions.find((option) => option.value === currentLang) || languageOptions[0]
  );

  function sectionFade() {
    return { duration: prefersReducedMotion.current ? 0 : 200 };
  }

  function sidebarBackdropFade() {
    return { duration: prefersReducedMotion.current ? 0 : 180 };
  }

  function changeLanguage(value: string): void {
    adminLanguageMenuOpen = false;
    clearAdminLanguageClickGuard();
    onLanguageChange(value, { section: "admin", adminSection: active });
  }

  function clearAdminLanguageClickGuard(): void {
    if (adminLanguageClickGuardTimer) {
      window.clearTimeout(adminLanguageClickGuardTimer);
      adminLanguageClickGuardTimer = null;
    }
    if (adminLanguageClickGuardArmTimer) {
      window.clearTimeout(adminLanguageClickGuardArmTimer);
      adminLanguageClickGuardArmTimer = null;
    }
    adminLanguageClickGuard = false;
    adminLanguageClickGuardArmed = false;
  }

  function setAdminLanguageMenuOpen(open: boolean): void {
    adminLanguageMenuOpen = Boolean(open);
    clearAdminLanguageClickGuard();
    if (!isCompact) return;
    if (adminLanguageMenuOpen) {
      adminLanguageClickGuard = true;
      adminLanguageClickGuardArmTimer = window.setTimeout(() => {
        adminLanguageClickGuardArmed = true;
        adminLanguageClickGuardArmTimer = null;
      }, 220);
      return;
    }
    adminLanguageClickGuard = true;
    adminLanguageClickGuardArmed = false;
    adminLanguageClickGuardTimer = window.setTimeout(() => {
      adminLanguageClickGuard = false;
      adminLanguageClickGuardTimer = null;
    }, 260);
  }

  function closeAdminLanguageFromGuard(event: MouseEvent | PointerEvent): void {
    event.preventDefault();
    event.stopPropagation();
    if (adminLanguageClickGuardArmed) setAdminLanguageMenuOpen(false);
  }

  onDestroy(() => {
    clearAdminLanguageClickGuard();
  });
</script>

<div
  class="admin-screen-wrap"
  class:is-sidebar-open={sidebarOpen}
  class:is-admin-language-open={adminLanguageGuardActive}
>
  {#if sidebarOpen}
    <button
      type="button"
      class="admin-sidebar-backdrop"
      aria-label={at("close_menu", {}, "Close menu")}
      in:fade={sidebarBackdropFade()}
      out:fade={sidebarBackdropFade()}
      onclick={() => (sidebarOpen = false)}
    ></button>
  {/if}
  {#if adminLanguageGuardActive}
    <button
      class="language-select-guard"
      class:language-select-guard--armed={adminLanguageClickGuardArmed}
      type="button"
      aria-label={t("wa_close", {}, at("close", {}, "Close"))}
      onpointerdown={closeAdminLanguageFromGuard}
      onclick={closeAdminLanguageFromGuard}
    ></button>
  {/if}
  <aside class="admin-sidebar" aria-label={at("sidebar_navigation", {}, "Admin navigation")}>
    <div class="admin-sidebar-brand">
      <BrandMark class="admin-brand-mark" {brand} />
      <div>
        <strong class="admin-brand-title">{brandTitle}</strong>
        <small>{at("panel_title", {}, "Admin Panel")}</small>
      </div>
      <AdminButton
        variant="ghost"
        size="icon"
        onclick={onClose}
        aria-label={at("exit", {}, "Exit")}
      >
        <ArrowLeft size={16} />
      </AdminButton>
    </div>

    {#each NAV_GROUPS as group}
      <div class="admin-sidebar-section-label">{group.label}</div>
      <nav class="admin-nav" aria-label={group.label}>
        {#each group.items as item}
          {@const NavIcon = dynamicComponent(item.icon)}
          <button
            type="button"
            class="admin-nav-item"
            class:active={active === item.id}
            data-admin-section={item.id}
            onfocus={() => warmSectionComponent(item)}
            onpointerenter={() => warmSectionComponent(item)}
            onclick={() => onSetActive(item.id)}
          >
            <NavIcon size={16} />
            <span>{item.label}</span>
            <span>
              {#if item.id === "support" && supportStore.stats?.total_unread_admin}
                <AdminBadge variant="danger">
                  <span class="numeric-badge-value">{supportStore.stats.total_unread_admin}</span>
                </AdminBadge>
              {/if}
            </span>
          </button>
        {/each}
      </nav>
    {/each}

    <div class="admin-sidebar-footer">
      {#if languageOptions.length}
        <div class="admin-language-switch">
          <Globe2 size={16} />
          <Select.Root
            type="single"
            bind:open={adminLanguageMenuOpen}
            value={currentLang}
            items={languageOptions}
            disabled={languageBusy}
            onOpenChange={setAdminLanguageMenuOpen}
            onValueChange={changeLanguage}
          >
            <Select.Trigger
              class="admin-language-trigger"
              aria-label={t("wa_settings_language", {}, at("language", {}, "Language"))}
            >
              <span>
                <strong>{t("wa_settings_language", {}, at("language", {}, "Language"))}</strong>
                <small>
                  <span class="emoji-flag" aria-hidden="true"
                    >{currentLanguageOption?.flag || "🏳️"}</span
                  >
                  {currentLanguageOption?.label || currentLang}
                </small>
              </span>
              <ChevronsUpDown size={14} />
            </Select.Trigger>
            <Select.Content class="language-select-content" side="top" align="start" sideOffset={8}>
              <Select.Viewport class="language-select-viewport">
                {#each languageOptions as option (option.value)}
                  <Select.Item
                    value={option.value}
                    label={option.label}
                    class="language-select-item"
                  >
                    <span class="language-select-item-main">
                      <span class="emoji-flag" aria-hidden="true">{option.flag}</span>
                      <span>{option.label}</span>
                    </span>
                    <Check size={15} class="language-select-item-check" />
                  </Select.Item>
                {/each}
              </Select.Viewport>
            </Select.Content>
          </Select.Root>
        </div>
      {/if}
      <a
        class="admin-version-link"
        href={appRepositoryUrl}
        target="_blank"
        rel="noopener noreferrer"
        title="Documentation"
      >
        <span>remnawave-minishop</span>
        <span>{appVersion || "dev+local"}</span>
      </a>
    </div>
  </aside>

  <section class="admin-content">
    <header class="admin-header">
      <div style="display:flex; align-items:center; gap:12px; min-width:0;">
        <button
          type="button"
          class="admin-mobile-toggle"
          onclick={() => (sidebarOpen = !sidebarOpen)}
          aria-label={at("menu", {}, "Menu")}
        >
          <Menu size={18} />
        </button>
        <div class="admin-header-title">
          <div class="admin-header-title-line">
            <h2>{meta.title}</h2>
            {#if active === "logs"}
              <span class="admin-header-count" title={at("total", {}, "Total")}
                >{Number(logsStore.logsTotal || 0)}</span
              >
            {/if}
          </div>
          {#if meta.subtitle}<small>{meta.subtitle}</small>{/if}
        </div>
      </div>
      <AdminHeaderActions
        {active}
        {at}
        {dirtyCount}
        {settingsSaving}
        {syncBusy}
        {translationsDirtyCount}
        {translationsSaving}
        onCreateAd={() => adsStore.setCreateOpen(true)}
        onCreateCode={() => promosStore.setCreateOpen(true)}
        onCreateTariff={tariffsStore.openCreateTariff}
        {onExportPayments}
        onSaveSettings={() => settingsStore.saveSettings(onSaveSettings)}
        onSaveTranslations={() => translationsStore.saveTranslations(onSaveTranslations)}
        onSyncStats={statsStore.triggerSync}
      />
    </header>

    <main class="admin-main">
      <ConfigAlertsBanner {at} section={active} onNavigate={onSetActive} />
      {#key active}
        <div
          class="admin-section-stage"
          data-admin-active-section={active}
          in:fade={sectionFade()}
          out:fade={sectionFade()}
        >
          {#if activeSectionComponent}
            {@const ActiveSectionComponent = activeSectionComponent}
            <ActiveSectionComponent
              {at}
              {availableFeatures}
              {brand}
              {currentLang}
              {fmtDate}
              {fmtDateShort}
              {fmtMoney}
              {featureAvailable}
              onSettingsSaved={onSaveSettings}
              onTranslationsSaved={onSaveTranslations}
              {paymentStatusVariant}
              {panelStatusBadge}
              {resolvedAvatarUrl}
              {routePrefix}
              {settingsPath}
              {userDisplayName}
              {userInitials}
              {userSecondaryName}
              {appFaviconUrl}
              {appFaviconUseCustom}
              {onOpenUserCard}
              {onOpenUsersFilter}
              {onUsersFiltersChange}
              {onOpenSettingsPath}
              {onSettingsPathChange}
              {initialTicketId}
              onNavigateSection={onSetActive}
            />
          {:else if activeSectionLoading}
            <div class="admin-section-loading" aria-busy="true" aria-live="polite">
              <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-short"></span>
              <span class="admin-skeleton admin-skeleton-line admin-skeleton-line-strong"></span>
              <span class="admin-skeleton admin-skeleton-line"></span>
            </div>
          {/if}
        </div>
      {/key}
    </main>
  </section>
</div>

<AdminLazyModals
  {at}
  {fmtDate}
  {fmtDateShort}
  {fmtMoney}
  {openTelegramProfileLink}
  {paymentStatusVariant}
  {resolvedAvatarUrl}
  {trafficLeftLabel}
  {trafficOfLabel}
  {trafficPercentValue}
  {userDisplayName}
  {userInitials}
  {userSecondaryName}
  {userTelegramProfileLink}
  {userTelegramProfileLinkKind}
  {onCloseUser}
  {onOpenPaymentUserCard}
  {routePrefix}
/>
