<script>
  import {
    ArrowLeft,
    Check,
    ChevronsUpDown,
    Coins,
    CreditCard,
    Download,
    FileText,
    Globe2,
    LayoutDashboard,
    Megaphone,
    Menu,
    Plus,
    RefreshCw,
    Save,
    Sliders,
    Sparkles,
    Tag,
    UsersRound,
  } from "lucide-svelte";
  import { onMount, setContext } from "svelte";
  import { Select } from "bits-ui";

  import BrandMark from "../BrandMark.svelte";
  import AdsSection from "./sections/AdsSection.svelte";
  import BroadcastSection from "./sections/BroadcastSection.svelte";
  import LogsSection from "./sections/LogsSection.svelte";
  import PaymentsSection from "./sections/PaymentsSection.svelte";
  import PromosSection from "./sections/PromosSection.svelte";
  import SettingsSection from "./sections/SettingsSection.svelte";
  import StatsSection from "./sections/StatsSection.svelte";
  import TariffEditorModal from "./sections/TariffEditorModal.svelte";
  import TariffsSection from "./sections/TariffsSection.svelte";
  import UserDetailModal from "./sections/UserDetailModal.svelte";
  import UsersSection from "./sections/UsersSection.svelte";
  import { createAdsStore } from "../lib/admin/stores/adsStore.js";
  import { createBroadcastStore } from "../lib/admin/stores/broadcastStore.js";
  import { createLogsStore } from "../lib/admin/stores/logsStore.js";
  import { createPaymentsStore } from "../lib/admin/stores/paymentsStore.js";
  import { createPromosStore } from "../lib/admin/stores/promosStore.js";
  import { createSettingsStore } from "../lib/admin/stores/settingsStore.js";
  import { createStatsStore } from "../lib/admin/stores/statsStore.js";
  import { createTariffsStore } from "../lib/admin/stores/tariffsStore.js";
  import { createUsersStore } from "../lib/admin/stores/usersStore.js";
  import {
    fmtDate,
    fmtDateShort,
    fmtMoney,
    optionLabel,
    paymentStatusVariant,
    trafficLeftLabel,
    trafficOfLabel,
    trafficPercentValue,
  } from "../lib/admin/format.js";
  import {
    createGravatarCache,
    userAvatarUrl,
    userDisplayName,
    userInitials,
    userSecondaryName,
  } from "../lib/admin/users.js";

  export let api;
  export let onClose = () => {};
  export let onToast = () => {};
  export let initialSection = "stats";
  export let initialUserId = null;
  export let onSectionChange = () => {};
  export let onSettingsSaved = () => {};
  export let onTariffsSaved = () => {};
  export let brandTitle = "/minishop";
  export let logoUrl = "";
  export let logoEmoji = "🫥";
  export let appVersion = "dev+local";
  export let appRepositoryUrl = "https://github.com/3252a8/remnawave-minishop";
  export let currentLang = "ru";
  export let languageOptions = [];
  export let languageBusy = false;
  export let onLanguageChange = () => {};
  export let t = (key, params = {}, fallback = "") => fallback || key;

  const at = (key, params = {}, fallback = "") => t(`admin_${key}`, params, fallback || key);

  $: NAV_GROUPS = [
    {
      id: "overview",
      label: at("nav_overview", {}, "Обзор"),
      items: [{ id: "stats", label: at("nav_dashboard", {}, "Дашборд"), icon: LayoutDashboard }],
    },
    {
      id: "operations",
      label: at("nav_operations", {}, "Управление"),
      items: [
        { id: "users", label: at("nav_users", {}, "Пользователи"), icon: UsersRound },
        { id: "payments", label: at("nav_payments", {}, "Платежи"), icon: CreditCard },
        { id: "promos", label: at("nav_promos", {}, "Промокоды"), icon: Tag },
        { id: "ads", label: at("nav_ads", {}, "Реклама"), icon: Sparkles },
      ],
    },
    {
      id: "communication",
      label: at("nav_communication", {}, "Коммуникации"),
      items: [
        { id: "broadcast", label: at("nav_broadcast", {}, "Рассылка"), icon: Megaphone },
        { id: "logs", label: at("nav_logs", {}, "Логи"), icon: FileText },
      ],
    },
    {
      id: "system",
      label: at("nav_system", {}, "Система"),
      items: [
        { id: "tariffs", label: at("nav_tariffs", {}, "Тарифы"), icon: Coins },
        { id: "settings", label: at("nav_settings", {}, "Настройки"), icon: Sliders },
      ],
    },
  ];

  $: SECTION_META = {
    stats: {
      title: at("section_stats_title", {}, "Дашборд"),
      subtitle: at("section_stats_subtitle", {}, "Аудитория, доходы, панель Remnawave и последние платежи"),
    },
    users: { title: at("section_users_title", {}, "Пользователи"), subtitle: at("section_users_subtitle", {}, "Поиск, баны и действия над аккаунтами") },
    payments: { title: at("section_payments_title", {}, "Платежи"), subtitle: at("section_payments_subtitle", {}, "История транзакций и экспорт") },
    promos: { title: at("section_promos_title", {}, "Промокоды"), subtitle: at("section_promos_subtitle", {}, "Создание и управление кодами") },
    ads: { title: at("section_ads_title", {}, "Рекламные кампании"), subtitle: at("section_ads_subtitle", {}, "UTM-источники и атрибуция") },
    broadcast: { title: at("section_broadcast_title", {}, "Рассылка"), subtitle: at("section_broadcast_subtitle", {}, "Массовая отправка сообщений в Telegram") },
    logs: { title: at("section_logs_title", {}, "Логи активности"), subtitle: at("section_logs_subtitle", {}, "События пользователей и админ-действия") },
    tariffs: { title: at("section_tariffs_title", {}, "Тарифы"), subtitle: at("section_tariffs_subtitle", {}, "Каталог продаж, периоды, пакеты и лимиты") },
    settings: { title: at("section_settings_title", {}, "Настройки приложения"), subtitle: at("section_settings_subtitle", {}, "Оверрайды над .env, применяются мгновенно") },
  };

  $: VALID_SECTIONS = (NAV_GROUPS || []).flatMap((group) => (group.items || []).map((item) => item.id));
  const normalizeSection = (value) => ((VALID_SECTIONS || []).includes(value) ? value : "stats");

  let active = normalizeSection(initialSection);
  $: if (initialSection) {
    active = normalizeSection(initialSection);
  }
  let sidebarOpen = false;
  let isCompact = false;

  function flash(text) {
    onToast(text);
  }

  const adsStore = createAdsStore({ api, onToast: flash, at });
  const broadcastStore = createBroadcastStore({ api, onToast: flash, at });
  const logsStore = createLogsStore({ api, at });
  const paymentsStore = createPaymentsStore({ api, at });
  const promosStore = createPromosStore({ api, onToast: flash, at });
  const settingsStore = createSettingsStore({ api, onToast: flash, at });
  const statsStore = createStatsStore({ api, onToast: flash, at });
  const tariffsStore = createTariffsStore({ api, onToast: flash, onTariffsSaved, flash, at });
  const usersStore = createUsersStore({ api, onToast: flash, at });

  setContext("promosStore", promosStore);
  setContext("adsStore", adsStore);
  setContext("broadcastStore", broadcastStore);
  setContext("logsStore", logsStore);
  setContext("paymentsStore", paymentsStore);
  setContext("statsStore", statsStore);
  setContext("settingsStore", settingsStore);
  setContext("usersStore", usersStore);
  setContext("tariffsStore", tariffsStore);

  $: usersStore.setActive(active);
  $: dirtyCount = Object.keys($settingsStore.settingsDirty || {}).length;
  $: syncBusy = $statsStore.syncBusy;
  $: settingsSaving = $settingsStore.settingsSaving;
  $: meta = SECTION_META[active] || { title: active, subtitle: "" };
  $: currentLanguageOption = languageOptions.find((option) => option.value === currentLang) || languageOptions[0];

  const gravatarCache = createGravatarCache(() => usersStore.updateState({}));

  function setActive(id) {
    const next = normalizeSection(id);
    sidebarOpen = false;
    if (active === next) return;
    active = next;
    usersStore.closeUser();
    onSectionChange(next);
  }

  function readSectionFromPath() {
    if (typeof window === "undefined") return "stats";
    const match = window.location.pathname.match(/^\/admin\/([a-z0-9_-]+)(?:\/[^/]+)?$/i);
    return normalizeSection(match ? match[1].toLowerCase() : "stats");
  }

  function readUserIdFromPath() {
    if (typeof window === "undefined") return null;
    const match = window.location.pathname.match(/^\/admin\/users\/(-?\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function onPopState() {
    active = readSectionFromPath();
    sidebarOpen = false;
    const userId = readUserIdFromPath();
    if (userId) {
      if (!$usersStore.openedUser || $usersStore.openedUser.user_id !== userId) {
        usersStore.openUser(userId, { skipPush: true });
      }
    } else if ($usersStore.openedUser) {
      usersStore.closeUser({ skipPush: true });
    }
  }

  function exportPayments() {
    if (typeof window === "undefined") return;
    window.open("/api/admin/payments/export.csv", "_blank", "noopener");
  }

  function resolvedAvatarUrl(user) {
    return userAvatarUrl(user) || (!user?.telegram_id && user?.email ? gravatarCache.gravatarUrl(user.email) : "");
  }

  function panelStatusBadge(user) {
    const status = String(user?.panel_status || "").toLowerCase();
    if (user?.is_banned) return { label: at("status_banned", {}, "Бан"), variant: "danger" };
    switch (status) {
      case "active":
        return { label: at("status_active", {}, "Active"), variant: "success" };
      case "expired":
        return {
          label: user?.panel_status_expired_at
            ? at("expired_badge", { date: fmtDateShort(user.panel_status_expired_at) }, `Expired ${fmtDateShort(user.panel_status_expired_at)}`)
            : at("status_expired", {}, "Expired"),
          variant: "warning",
        };
      case "limited":
        return { label: at("status_limited", {}, "Limited"), variant: "warning" };
      case "disabled":
        return { label: at("status_disabled", {}, "Disabled"), variant: "muted" };
      case "bot_only":
        return { label: at("status_bot_only", {}, "Только бот"), variant: "muted" };
      default:
        return { label: status || "—", variant: "muted" };
    }
  }

  let compactMql = null;
  function onCompactChange(event) {
    isCompact = Boolean(event?.matches);
  }

  onMount(() => {
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      compactMql = window.matchMedia("(max-width: 720px)");
      isCompact = compactMql.matches;
      if (compactMql.addEventListener) compactMql.addEventListener("change", onCompactChange);
      else if (compactMql.addListener) compactMql.addListener(onCompactChange);
    }
    if (typeof window !== "undefined") {
      window.addEventListener("popstate", onPopState);
    }
    return () => {
      if (compactMql) {
        if (compactMql.removeEventListener) compactMql.removeEventListener("change", onCompactChange);
        else if (compactMql.removeListener) compactMql.removeListener(onCompactChange);
      }
      if (typeof window !== "undefined") window.removeEventListener("popstate", onPopState);
    };
  });

  $: if (active === "users" && initialUserId && (!$usersStore.openedUser || $usersStore.openedUser.user_id !== initialUserId)) {
    usersStore.openUser(initialUserId, { skipPush: true });
  }
</script>

<div class="admin-screen-wrap" class:is-sidebar-open={sidebarOpen}>
  {#if sidebarOpen}
    <button type="button" class="admin-sidebar-backdrop" aria-label={at("close_menu", {}, "Закрыть меню")} on:click={() => (sidebarOpen = false)}></button>
  {/if}

  <aside class="admin-sidebar" aria-label={at("sidebar_navigation", {}, "Навигация админки")}>
    <div class="admin-sidebar-brand">
      <BrandMark class="admin-brand-mark" logoUrl={logoUrl} emoji={logoEmoji} />
      <div>
        <strong class="admin-brand-title">{brandTitle}</strong>
        <small>{at("panel_title", {}, "Админ-панель")}</small>
      </div>
      <button type="button" class="admin-btn admin-btn-icon admin-btn-ghost" on:click={onClose} aria-label={at("exit", {}, "Выйти")}>
        <ArrowLeft size={16} />
      </button>
    </div>

    {#each NAV_GROUPS as group}
      <div class="admin-sidebar-section-label">{group.label}</div>
      <nav class="admin-nav" aria-label={group.label}>
        {#each group.items as item}
          <button type="button" class="admin-nav-item" class:active={active === item.id} on:click={() => setActive(item.id)}>
            <svelte:component this={item.icon} size={16} />
            <span>{item.label}</span>
            <span></span>
          </button>
        {/each}
      </nav>
    {/each}

    <div class="admin-sidebar-footer">
      {#if languageOptions.length}
        <div class="admin-language-switch">
          <Globe2 size={16} />
          <Select.Root type="single" value={currentLang} items={languageOptions} disabled={languageBusy} onValueChange={onLanguageChange}>
            <Select.Trigger class="admin-language-trigger" aria-label={t("wa_settings_language", {}, at("language", {}, "Язык"))}>
              <span>
                <strong>{t("wa_settings_language", {}, at("language", {}, "Язык"))}</strong>
                <small>
                  <span class="emoji-flag" aria-hidden="true">{currentLanguageOption?.flag || "🏳️"}</span>
                  {currentLanguageOption?.label || currentLang}
                </small>
              </span>
              <ChevronsUpDown size={14} />
            </Select.Trigger>
            <Select.Content class="language-select-content" side="top" align="start" sideOffset={8}>
              <Select.Viewport class="language-select-viewport">
                {#each languageOptions as option (option.value)}
                  <Select.Item value={option.value} label={option.label} class="language-select-item">
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
      <a class="admin-version-link" href={appRepositoryUrl} target="_blank" rel="noopener noreferrer" title="GitHub">
        <span>remnawave-minishop</span>
        <span>{appVersion || "dev+local"}</span>
      </a>
    </div>
  </aside>

  <section class="admin-content">
    <header class="admin-header">
      <div style="display:flex; align-items:center; gap:12px; min-width:0;">
        <button type="button" class="admin-mobile-toggle" on:click={() => (sidebarOpen = !sidebarOpen)} aria-label={at("menu", {}, "Меню")}>
          <Menu size={18} />
        </button>
        <div class="admin-header-title">
          <h2>{meta.title}</h2>
          {#if meta.subtitle}<small>{meta.subtitle}</small>{/if}
        </div>
      </div>
      <div class="admin-header-actions">
        {#if active === "stats"}
          <button type="button" class="admin-btn" on:click={statsStore.triggerSync} disabled={syncBusy}>
            <RefreshCw size={14} /> {syncBusy ? at("btn_syncing", {}, "Синхронизация...") : at("btn_sync", {}, "Синхронизировать")}
          </button>
        {/if}
        {#if active === "payments"}
          <button type="button" class="admin-btn" on:click={exportPayments}>
            <Download size={14} /> CSV
          </button>
        {/if}
        {#if active === "promos"}
          <button type="button" class="admin-btn admin-btn-primary" on:click={() => promosStore.setCreateOpen(true)}>
            <Plus size={14} /> {at("btn_create", {}, "Создать")}
          </button>
        {/if}
        {#if active === "ads"}
          <button type="button" class="admin-btn admin-btn-primary" on:click={() => adsStore.setCreateOpen(true)}>
            <Plus size={14} /> {at("btn_campaign", {}, "Кампания")}
          </button>
        {/if}
        {#if active === "tariffs"}
          <button type="button" class="admin-btn admin-btn-primary" on:click={tariffsStore.openCreateTariff}>
            <Plus size={14} /> {at("btn_tariff", {}, "Тариф")}
          </button>
        {/if}
        {#if active === "settings"}
          {#if dirtyCount}
            <span class="admin-badge admin-badge-warning">{at("settings_dirty_count", { count: dirtyCount }, "Изменений: " + dirtyCount)}</span>
          {/if}
          <button type="button" class="admin-btn admin-btn-primary" on:click={() => settingsStore.saveSettings(onSettingsSaved)} disabled={!dirtyCount || settingsSaving}>
            <Save size={14} /> {settingsSaving ? at("btn_saving", {}, "Сохранение...") : at("btn_save", {}, "Сохранить")}
          </button>
        {/if}
      </div>
    </header>

    <main class="admin-main">
      {#if active === "stats"}
        <StatsSection {at} {fmtDate} {fmtDateShort} {fmtMoney} {paymentStatusVariant} />
      {/if}

      {#if active === "users"}
        <UsersSection
          {at}
          {fmtDateShort}
          {optionLabel}
          {panelStatusBadge}
          {resolvedAvatarUrl}
          {userDisplayName}
          {userInitials}
          {userSecondaryName}
        />
      {/if}

      {#if active === "payments"}
        <PaymentsSection {at} {fmtDate} {fmtMoney} {paymentStatusVariant} />
      {/if}

      {#if active === "promos"}
        <PromosSection {at} {fmtDateShort} />
      {/if}

      {#if active === "ads"}
        <AdsSection {at} {fmtMoney} />
      {/if}

      {#if active === "broadcast"}
        <BroadcastSection {at} {optionLabel} />
      {/if}

      {#if active === "logs"}
        <LogsSection {at} {fmtDate} />
      {/if}

      {#if active === "tariffs"}
        <TariffsSection {at} {fmtMoney} />
      {/if}

      {#if active === "settings"}
        <SettingsSection {at} {isCompact} {onSettingsSaved} />
      {/if}
    </main>
  </section>
</div>

<TariffEditorModal {at} />

<UserDetailModal
  {at}
  {fmtDate}
  {fmtDateShort}
  {fmtMoney}
  {resolvedAvatarUrl}
  {userDisplayName}
  {userSecondaryName}
  {userInitials}
  {paymentStatusVariant}
  {trafficPercentValue}
  {trafficLeftLabel}
  {trafficOfLabel}
/>
