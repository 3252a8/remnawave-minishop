<script>
  import {
    ArrowLeft,
    Check,
    ChevronsUpDown,
    Coins,
    CreditCard,
    Database,
    Download,
    FileText,
    Globe2,
    Languages,
    LayoutDashboard,
    LifeBuoy,
    Megaphone,
    Menu,
    Paintbrush,
    Plus,
    RefreshCw,
    Save,
    Sliders,
    Sparkles,
    Tag,
    UsersRound,
  } from "$components/ui/icons.js";
  import { onMount, setContext } from "svelte";
  import { fade } from "svelte/transition";
  import { Select } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import AdsSection from "./sections/AdsSection.svelte";
  import BackupsSection from "./sections/BackupsSection.svelte";
  import BroadcastSection from "./sections/BroadcastSection.svelte";
  import LogsSection from "./sections/LogsSection.svelte";
  import PaymentDetailModal from "./sections/PaymentDetailModal.svelte";
  import PaymentsSection from "./sections/PaymentsSection.svelte";
  import PromosSection from "./sections/PromosSection.svelte";
  import SettingsSection from "./sections/SettingsSection.svelte";
  import StatsSection from "./sections/StatsSection.svelte";
  import SupportSection from "./sections/SupportSection.svelte";
  import TariffEditorModal from "./sections/TariffEditorModal.svelte";
  import TariffsSection from "./sections/TariffsSection.svelte";
  import TranslationsSection from "./sections/TranslationsSection.svelte";
  import AppearanceSection from "./sections/AppearanceSection.svelte";
  import UserDetailModal from "./sections/UserDetailModal.svelte";
  import UsersSection from "./sections/UsersSection.svelte";
  import { createAdsStore } from "../lib/admin/stores/adsStore.js";
  import { createBackupsStore } from "../lib/admin/stores/backupsStore.js";
  import { createBroadcastStore } from "../lib/admin/stores/broadcastStore.js";
  import { createLogsStore } from "../lib/admin/stores/logsStore.js";
  import { createPaymentsStore } from "../lib/admin/stores/paymentsStore.js";
  import { createPromosStore } from "../lib/admin/stores/promosStore.js";
  import { createSettingsStore } from "../lib/admin/stores/settingsStore.js";
  import { createStatsStore } from "../lib/admin/stores/statsStore.js";
  import { createAdminSupportStore } from "../lib/admin/stores/supportStore.js";
  import { createTariffsStore } from "../lib/admin/stores/tariffsStore.js";
  import { createThemesStore } from "../lib/admin/stores/themesStore.js";
  import { createTranslationsStore } from "../lib/admin/stores/translationsStore.js";
  import { createUsersStore } from "../lib/admin/stores/usersStore.js";
  import {
    fmtDate,
    fmtDateShort,
    fmtMoney,
    paymentStatusVariant,
    trafficLeftLabel,
    trafficOfLabel,
    trafficPercentValue,
  } from "../lib/admin/format.js";
  import {
    createGravatarCache,
    openTelegramProfileLink,
    userAvatarUrl,
    userDisplayName,
    userInitials,
    userSecondaryName,
    userTelegramProfileLink,
    userTelegramProfileLinkKind,
  } from "../lib/admin/users.js";
  import { stripRoutePrefix } from "../lib/webapp/routes.js";

  export let api;
  export let onClose = () => {};
  export let onToast = () => {};
  export let initialSection = "stats";
  export let initialPaymentId = null;
  export let initialPaymentUserId = null;
  export let initialUserId = null;
  export let onSectionChange = () => {};
  export let onSettingsSaved = () => {};
  export let onTariffsSaved = () => {};
  export let onThemesSaved = () => {};
  export let onTranslationsSaved = () => {};
  export let routePrefix = "";
  export let brand = {};
  export let brandTitle = "/minishop";
  export let appFaviconUrl = "";
  export let appFaviconUseCustom = false;
  export let appVersion = "dev+local";
  export let appRepositoryUrl = "https://github.com/3252a8/remnawave-minishop";
  export let currentLang = "ru";
  export let languageOptions = [];
  export let languageBusy = false;
  export let onLanguageChange = () => {};
  export let t = (key, _params = {}, fallback = "") => fallback || key;

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
        { id: "support", label: at("nav_support", {}, "Поддержка"), icon: LifeBuoy },
      ],
    },
    {
      id: "system",
      label: at("nav_system", {}, "Система"),
      items: [
        { id: "tariffs", label: at("nav_tariffs", {}, "Тарифы"), icon: Coins },
        { id: "appearance", label: at("nav_appearance", {}, "Внешний вид"), icon: Paintbrush },
        { id: "translations", label: at("nav_translations", {}, "Переводы"), icon: Languages },
        { id: "backups", label: at("nav_backups", {}, "Бэкапы"), icon: Database },
        { id: "settings", label: at("nav_settings", {}, "Настройки"), icon: Sliders },
      ],
    },
  ];

  $: SECTION_META = {
    stats: {
      title: at("section_stats_title", {}, "Дашборд"),
      subtitle: at(
        "section_stats_subtitle",
        {},
        "Аудитория, доходы, панель Remnawave и последние платежи"
      ),
    },
    users: {
      title: at("section_users_title", {}, "Пользователи"),
      subtitle: at("section_users_subtitle", {}, "Поиск, баны и действия над аккаунтами"),
    },
    payments: {
      title: at("section_payments_title", {}, "Платежи"),
      subtitle: at("section_payments_subtitle", {}, "История транзакций и экспорт"),
    },
    promos: {
      title: at("section_promos_title", {}, "Промокоды"),
      subtitle: at("section_promos_subtitle", {}, "Создание и управление кодами"),
    },
    ads: {
      title: at("section_ads_title", {}, "Рекламные кампании"),
      subtitle: at("section_ads_subtitle", {}, "UTM-источники и атрибуция"),
    },
    broadcast: {
      title: at("section_broadcast_title", {}, "Рассылка"),
      subtitle: at("section_broadcast_subtitle", {}, "Массовая отправка сообщений в Telegram"),
    },
    logs: {
      title: at("section_logs_title", {}, "Логи активности"),
      subtitle: at("section_logs_subtitle", {}, "События пользователей и админ-действия"),
    },
    support: {
      title: at("section_support_title", {}, "Поддержка"),
      subtitle: at("section_support_subtitle", {}, "Инбокс тикетов и ответы пользователям"),
    },
    tariffs: {
      title: at("section_tariffs_title", {}, "Тарифы"),
      subtitle: at("section_tariffs_subtitle", {}, "Каталог продаж, периоды, пакеты и лимиты"),
    },
    appearance: {
      title: at("section_appearance_title", {}, "Внешний вид"),
      subtitle: at("section_appearance_subtitle", {}, "Логотип, темы и акцентные цвета Mini App"),
    },
    translations: {
      title: at("section_translations_title", {}, "Переводы"),
      subtitle: at(
        "section_translations_subtitle",
        {},
        "Оверрайды строк локализации из базы данных и data/locales-overrides.json"
      ),
    },
    backups: {
      title: at("section_backups_title", {}, "Бэкапы"),
      subtitle: at("section_backups_subtitle", {}, "Архивы, загрузка и восстановление БД/compose"),
    },
    settings: {
      title: at("section_settings_title", {}, "Настройки приложения"),
      subtitle: at("section_settings_subtitle", {}, "Оверрайды над .env, применяются мгновенно"),
    },
  };

  $: VALID_SECTIONS = (NAV_GROUPS || []).flatMap((group) =>
    (group.items || []).map((item) => item.id)
  );
  const normalizeSection = (value) => ((VALID_SECTIONS || []).includes(value) ? value : "stats");

  let active = normalizeSection(initialSection);
  let lastInitialSection = active;
  $: {
    const nextInitialSection = normalizeSection(initialSection);
    if (nextInitialSection !== lastInitialSection) {
      active = nextInitialSection;
      lastInitialSection = nextInitialSection;
    }
  }
  let sidebarOpen = false;
  let isCompact = false;
  let adminLanguageMenuOpen = false;
  let adminLanguageClickGuard = false;
  let adminLanguageClickGuardArmed = false;
  let adminLanguageClickGuardTimer = null;
  let adminLanguageClickGuardArmTimer = null;
  $: adminLanguageGuardActive = isCompact && (adminLanguageMenuOpen || adminLanguageClickGuard);

  function readReduceMotion() {
    return (
      typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  let reduceMotion = readReduceMotion();

  function flash(text) {
    onToast(text);
  }

  const adsStore = createAdsStore({ api, onToast: flash, at });
  const backupsStore = createBackupsStore({ api, onToast: flash, at });
  const broadcastStore = createBroadcastStore({ api, onToast: flash, at });
  const logsStore = createLogsStore({ api, at });
  const paymentsStore = createPaymentsStore({ api, onToast: flash, at, routePrefix });
  const promosStore = createPromosStore({ api, onToast: flash, at });
  const settingsStore = createSettingsStore({ api, onToast: flash, at });
  const statsStore = createStatsStore({ api, onToast: flash, at });
  const supportStore = createAdminSupportStore({ api, onToast: flash, at, routePrefix });
  const tariffsStore = createTariffsStore({ api, onToast: flash, onTariffsSaved, flash, at });
  const themesStore = createThemesStore({ api, onThemesSaved, flash, at });
  const translationsStore = createTranslationsStore({ api, onToast: flash, at });
  const usersStore = createUsersStore({ api, onToast: flash, at, routePrefix });

  setContext("promosStore", promosStore);
  setContext("adsStore", adsStore);
  setContext("backupsStore", backupsStore);
  setContext("broadcastStore", broadcastStore);
  setContext("logsStore", logsStore);
  setContext("paymentsStore", paymentsStore);
  setContext("statsStore", statsStore);
  setContext("adminSupportStore", supportStore);
  setContext("settingsStore", settingsStore);
  setContext("usersStore", usersStore);
  setContext("tariffsStore", tariffsStore);
  setContext("themesStore", themesStore);
  setContext("translationsStore", translationsStore);

  $: usersStore.setActive(active);
  $: paymentsStore.setActive(active);
  $: supportStore.setActive(active);
  $: dirtyCount = Object.keys($settingsStore.settingsDirty || {}).length;
  $: translationsDirtyCount = Object.keys($translationsStore.translationsDirty || {}).length;
  $: syncBusy = $statsStore.syncBusy;
  $: settingsSaving = $settingsStore.settingsSaving;
  $: translationsSaving = $translationsStore.translationsSaving;
  $: meta = SECTION_META[active] || { title: active, subtitle: "" };
  $: currentLanguageOption =
    languageOptions.find((option) => option.value === currentLang) || languageOptions[0];

  const gravatarCache = createGravatarCache(() => usersStore.updateState({}));

  function setActive(id) {
    const next = normalizeSection(id);
    sidebarOpen = false;
    if (active === next) return;
    active = next;
    usersStore.closeUser();
    paymentsStore.closePayment();
    supportStore.closeTicketView();
    onSectionChange(next);
  }

  function changeLanguage(value) {
    adminLanguageMenuOpen = false;
    clearAdminLanguageClickGuard();
    onLanguageChange(value, { section: "admin", adminSection: active });
  }

  function currentRoutePathname() {
    if (typeof window === "undefined") return "/";
    return stripRoutePrefix(window.location.pathname, routePrefix);
  }

  function readSectionFromPath() {
    if (typeof window === "undefined") return "stats";
    const match = currentRoutePathname().match(/^\/admin\/([a-z0-9_-]+)(?:\/.*)?$/i);
    return normalizeSection(match ? match[1].toLowerCase() : "stats");
  }

  function readUserIdFromPath() {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/users\/(-?\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function readSupportTicketIdFromPath() {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/support\/(\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function readPaymentIdFromPath() {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/payments\/(\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function readPaymentUserIdFromPath() {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/payments\/users\/(-?\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function onPopState() {
    active = readSectionFromPath();
    sidebarOpen = false;
    const userId = readUserIdFromPath();
    const paymentUserId = active === "payments" ? readPaymentUserIdFromPath() : null;
    const contextualUserId = paymentUserId || userId;
    if (contextualUserId) {
      if (!$usersStore.openedUser || $usersStore.openedUser.user_id !== contextualUserId) {
        usersStore.openUser(contextualUserId, {
          skipPush: true,
          pathContext: paymentUserId ? "payments" : "users",
        });
      }
    } else if ($usersStore.openedUser) {
      usersStore.closeUser({ skipPush: true });
    }
    const paymentId = readPaymentIdFromPath();
    if (active === "payments" && paymentId) {
      if (!$paymentsStore.openedPaymentId || $paymentsStore.openedPaymentId !== paymentId) {
        paymentsStore.openPayment(paymentId, { skipPush: true });
      }
    } else if ($paymentsStore.openedPaymentId) {
      paymentsStore.closePayment({ skipPush: true });
    }
    const ticketId = readSupportTicketIdFromPath();
    if (active === "support" && ticketId) {
      if (!$supportStore.openedTicketId || $supportStore.openedTicketId !== ticketId) {
        supportStore.openTicket(ticketId, { skipPush: true });
      }
    } else if (active === "support" && $supportStore.openedTicketId) {
      supportStore.closeTicketView({ skipPush: true });
    }
  }

  function exportPayments() {
    if (typeof window === "undefined") return;
    window.open("/api/admin/payments/export.csv", "_blank", "noopener");
  }

  function openPaymentUserCard(userId) {
    const uid = Number(userId);
    // Synthetic email-only users use negative user_id; still a valid admin target.
    if (!Number.isFinite(uid) || uid === 0) return;
    const next = normalizeSection("payments");
    sidebarOpen = false;
    if (active !== next) {
      active = next;
      usersStore.closeUser();
      paymentsStore.closePayment({ skipPush: true });
      onSectionChange(next);
    }
    usersStore.setActive(next);
    paymentsStore.closePayment({ skipPush: true });
    usersStore.openUser(uid, { pathContext: "payments" });
  }

  function openLogsUserCard(userId) {
    const uid = Number(userId);
    if (!Number.isFinite(uid) || uid === 0) return;
    const next = normalizeSection("logs");
    sidebarOpen = false;
    if (active !== next) {
      active = next;
      paymentsStore.closePayment({ skipPush: true });
      supportStore.closeTicketView({ skipPush: true });
      onSectionChange(next);
    }
    usersStore.setActive(next);
    usersStore.openUser(uid, { skipPush: true, pathContext: "logs" });
  }

  function openUserCard(userId) {
    const uid = Number(userId);
    if (!Number.isFinite(uid) || uid === 0) return;
    const next = normalizeSection("users");
    sidebarOpen = false;
    if (active !== next) {
      active = next;
      paymentsStore.closePayment({ skipPush: true });
      supportStore.closeTicketView({ skipPush: true });
      onSectionChange(next, uid);
    }
    usersStore.setActive(next);
    usersStore.openUser(uid);
  }

  function resolvedAvatarUrl(user) {
    return userAvatarUrl(user) || (user?.email ? gravatarCache.gravatarUrl(user.email) : "");
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
            ? at(
                "expired_badge",
                { date: fmtDateShort(user.panel_status_expired_at) },
                `Expired ${fmtDateShort(user.panel_status_expired_at)}`
              )
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

  function clearAdminLanguageClickGuard() {
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

  function setAdminLanguageMenuOpen(open) {
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

  function closeAdminLanguageFromGuard(event) {
    event.preventDefault();
    event.stopPropagation();
    if (adminLanguageClickGuardArmed) setAdminLanguageMenuOpen(false);
  }

  onMount(() => {
    reduceMotion = readReduceMotion();
    let motionMql = null;
    const onMotionChange = () => {
      reduceMotion = readReduceMotion();
    };
    if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      motionMql = window.matchMedia("(prefers-reduced-motion: reduce)");
      reduceMotion = motionMql.matches;
      motionMql.addEventListener("change", onMotionChange);
    }
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
      if (motionMql) motionMql.removeEventListener("change", onMotionChange);
      if (compactMql) {
        if (compactMql.removeEventListener)
          compactMql.removeEventListener("change", onCompactChange);
        else if (compactMql.removeListener) compactMql.removeListener(onCompactChange);
      }
      if (typeof window !== "undefined") window.removeEventListener("popstate", onPopState);
      clearAdminLanguageClickGuard();
    };
  });

  $: sectionFade = reduceMotion ? { duration: 0 } : { duration: 200 };
  $: sidebarBackdropFade = reduceMotion ? { duration: 0 } : { duration: 180 };

  $: if (
    active === "users" &&
    initialUserId &&
    (!$usersStore.openedUser || $usersStore.openedUser.user_id !== initialUserId)
  ) {
    usersStore.openUser(initialUserId, { skipPush: true });
  }

  $: if (
    active === "payments" &&
    initialPaymentId &&
    (!$paymentsStore.openedPaymentId || $paymentsStore.openedPaymentId !== initialPaymentId)
  ) {
    paymentsStore.openPayment(initialPaymentId, { skipPush: true });
  }

  $: if (
    active === "payments" &&
    initialPaymentUserId &&
    (!$usersStore.openedUser || $usersStore.openedUser.user_id !== initialPaymentUserId)
  ) {
    usersStore.openUser(initialPaymentUserId, { skipPush: true, pathContext: "payments" });
  }
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
      aria-label={at("close_menu", {}, "Закрыть меню")}
      in:fade={sidebarBackdropFade}
      out:fade={sidebarBackdropFade}
      on:click={() => (sidebarOpen = false)}
    ></button>
  {/if}
  {#if adminLanguageGuardActive}
    <button
      class="language-select-guard"
      class:language-select-guard--armed={adminLanguageClickGuardArmed}
      type="button"
      aria-label={t("wa_close", {}, at("close", {}, "Закрыть"))}
      on:pointerdown={closeAdminLanguageFromGuard}
      on:click={closeAdminLanguageFromGuard}
    ></button>
  {/if}
  <aside class="admin-sidebar" aria-label={at("sidebar_navigation", {}, "Навигация админки")}>
    <div class="admin-sidebar-brand">
      <BrandMark class="admin-brand-mark" {brand} />
      <div>
        <strong class="admin-brand-title">{brandTitle}</strong>
        <small>{at("panel_title", {}, "Админ-панель")}</small>
      </div>
      <AdminButton
        variant="ghost"
        size="icon"
        onclick={onClose}
        aria-label={at("exit", {}, "Выйти")}
      >
        <ArrowLeft size={16} />
      </AdminButton>
    </div>

    {#each NAV_GROUPS as group}
      <div class="admin-sidebar-section-label">{group.label}</div>
      <nav class="admin-nav" aria-label={group.label}>
        {#each group.items as item}
          <button
            type="button"
            class="admin-nav-item"
            class:active={active === item.id}
            on:click={() => setActive(item.id)}
          >
            <svelte:component this={item.icon} size={16} />
            <span>{item.label}</span>
            <span>
              {#if item.id === "support" && $supportStore.stats?.total_unread_admin}
                <AdminBadge variant="danger">
                  <span class="numeric-badge-value">{$supportStore.stats.total_unread_admin}</span>
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
              aria-label={t("wa_settings_language", {}, at("language", {}, "Язык"))}
            >
              <span>
                <strong>{t("wa_settings_language", {}, at("language", {}, "Язык"))}</strong>
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
        title="GitHub"
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
          on:click={() => (sidebarOpen = !sidebarOpen)}
          aria-label={at("menu", {}, "Меню")}
        >
          <Menu size={18} />
        </button>
        <div class="admin-header-title">
          <h2>{meta.title}</h2>
          {#if meta.subtitle}<small>{meta.subtitle}</small>{/if}
        </div>
      </div>
      <div class="admin-header-actions">
        {#if active === "stats"}
          <AdminButton onclick={statsStore.triggerSync} disabled={syncBusy}>
            <RefreshCw size={14} />
            {syncBusy
              ? at("btn_syncing", {}, "Синхронизация...")
              : at("btn_sync", {}, "Синхронизировать")}
          </AdminButton>
        {/if}
        {#if active === "payments"}
          <AdminButton onclick={exportPayments}>
            <Download size={14} /> CSV
          </AdminButton>
        {/if}
        {#if active === "promos"}
          <AdminButton variant="primary" onclick={() => promosStore.setCreateOpen(true)}>
            <Plus size={14} />
            {at("btn_create", {}, "Создать")}
          </AdminButton>
        {/if}
        {#if active === "ads"}
          <AdminButton variant="primary" onclick={() => adsStore.setCreateOpen(true)}>
            <Plus size={14} />
            {at("btn_campaign", {}, "Кампания")}
          </AdminButton>
        {/if}
        {#if active === "tariffs"}
          <AdminButton variant="primary" onclick={tariffsStore.openCreateTariff}>
            <Plus size={14} />
            {at("btn_tariff", {}, "Тариф")}
          </AdminButton>
        {/if}
        {#if active === "settings"}
          {#if dirtyCount}
            <AdminBadge variant="warning"
              >{at(
                "settings_dirty_count",
                { count: dirtyCount },
                "Изменений: " + dirtyCount
              )}</AdminBadge
            >
          {/if}
          <AdminButton
            variant="primary"
            onclick={() => settingsStore.saveSettings(onSettingsSaved)}
            disabled={!dirtyCount || settingsSaving}
          >
            <Save size={14} />
            {settingsSaving
              ? at("btn_saving", {}, "Сохранение...")
              : at("btn_save", {}, "Сохранить")}
          </AdminButton>
        {/if}
        {#if active === "translations"}
          {#if translationsDirtyCount}
            <AdminBadge variant="warning"
              >{at(
                "settings_dirty_count",
                { count: translationsDirtyCount },
                "Изменений: " + translationsDirtyCount
              )}</AdminBadge
            >
          {/if}
          <AdminButton
            variant="primary"
            onclick={() => translationsStore.saveTranslations(onTranslationsSaved)}
            disabled={!translationsDirtyCount || translationsSaving}
          >
            <Save size={14} />
            {translationsSaving
              ? at("btn_saving", {}, "Сохранение...")
              : at("btn_save", {}, "Сохранить")}
          </AdminButton>
        {/if}
      </div>
    </header>

    <main class="admin-main">
      {#key active}
        <div class="admin-section-stage" in:fade={sectionFade} out:fade={sectionFade}>
          {#if active === "stats"}
            <StatsSection {at} {fmtDate} {fmtDateShort} {fmtMoney} {paymentStatusVariant} />
          {/if}

          {#if active === "users"}
            <UsersSection
              {at}
              {fmtDateShort}
              {fmtMoney}
              {panelStatusBadge}
              {resolvedAvatarUrl}
              {userDisplayName}
              {userInitials}
              {userSecondaryName}
            />
          {/if}

          {#if active === "payments"}
            <PaymentsSection
              {at}
              {fmtDate}
              {fmtMoney}
              {paymentStatusVariant}
              onOpenUserCard={openPaymentUserCard}
            />
          {/if}

          {#if active === "promos"}
            <PromosSection {at} {fmtDateShort} />
          {/if}

          {#if active === "ads"}
            <AdsSection {at} {fmtMoney} />
          {/if}

          {#if active === "broadcast"}
            <BroadcastSection {at} />
          {/if}

          {#if active === "logs"}
            <LogsSection {at} {fmtDate} onOpenUserCard={openLogsUserCard} />
          {/if}

          {#if active === "support"}
            <SupportSection
              {at}
              {brand}
              {resolvedAvatarUrl}
              onOpenUserCard={openUserCard}
              initialTicketId={readSupportTicketIdFromPath()}
            />
          {/if}

          {#if active === "tariffs"}
            <TariffsSection {at} {fmtMoney} {onSettingsSaved} />
          {/if}

          {#if active === "appearance"}
            <AppearanceSection
              {at}
              {currentLang}
              {onSettingsSaved}
              {brand}
              {appFaviconUrl}
              {appFaviconUseCustom}
            />
          {/if}

          {#if active === "settings"}
            <SettingsSection {at} {onSettingsSaved} {currentLang} />
          {/if}

          {#if active === "backups"}
            <BackupsSection {at} {fmtDate} />
          {/if}

          {#if active === "translations"}
            <TranslationsSection {at} {onTranslationsSaved} />
          {/if}
        </div>
      {/key}
    </main>
  </section>
</div>

<TariffEditorModal {at} />

<PaymentDetailModal
  {at}
  {fmtDate}
  {fmtMoney}
  {paymentStatusVariant}
  onOpenUserCard={openPaymentUserCard}
/>

<UserDetailModal
  {at}
  {fmtDate}
  {fmtDateShort}
  {fmtMoney}
  {resolvedAvatarUrl}
  {userDisplayName}
  {userSecondaryName}
  {userInitials}
  {userTelegramProfileLink}
  {userTelegramProfileLinkKind}
  {openTelegramProfileLink}
  {paymentStatusVariant}
  {trafficPercentValue}
  {trafficLeftLabel}
  {trafficOfLabel}
/>
