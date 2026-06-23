<script lang="ts">
  import { QueryClient } from "@tanstack/svelte-query";
  import {
    ArrowLeft,
    Check,
    ChevronsUpDown,
    Download,
    Globe2,
    Menu,
    Plus,
    RefreshCw,
    Save,
  } from "$components/ui/icons.js";
  import { onMount, setContext } from "svelte";
  import { fade } from "svelte/transition";
  import { Select } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import PaymentDetailModal from "./sections/PaymentDetailModal.svelte";
  import TariffEditorModal from "./sections/TariffEditorModal.svelte";
  import UserDetailModal from "./sections/UserDetailModal.svelte";
  import { ADMIN_SECTION_GROUPS, ADMIN_SECTIONS } from "./sections/registry";
  import ConfigAlertsBanner from "./ConfigAlertsBanner.svelte";
  import { createAdsStore } from "../lib/admin/stores/adsStore.js";
  import { createBackupsStore } from "../lib/admin/stores/backupsStore.js";
  import { createBroadcastStore } from "../lib/admin/stores/broadcastStore.js";
  import { createHealthStore } from "../lib/admin/stores/healthStore.js";
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
  import {
    adminSettingsPathFromPath,
    stripRoutePrefix,
    withRoutePrefix,
  } from "../lib/webapp/routes.js";
  import type { AdminSectionDescriptor } from "./sections/registry";
  import type { SettingsSavedPayload } from "../lib/admin/stores/settingsStore";
  import type { TariffsCatalog } from "../lib/admin/stores/tariffsStore";
  import type { TranslationsSavedPayload } from "../lib/admin/stores/translationsStore";
  import type { AdminUser } from "../lib/admin/stores/usersStore";
  import type { ComponentType, SvelteComponent } from "svelte";

  type AdminApi = Parameters<typeof createAdsStore>[0]["api"] &
    Parameters<typeof createThemesStore>[0]["api"];
  type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
  type AdminSectionId = string;
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
  type PanelStatusBadge = { label: string; variant: "success" | "danger" | "warning" | "muted" };
  type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

  export let api: AdminApi;
  export let onClose: () => void = () => {};
  export let onToast: (message: string) => void = () => {};
  export let initialSection = "stats";
  export let initialSettingsPath: SettingsPath = [];
  export let initialPaymentId: number | null = null;
  export let initialPaymentUserId: number | null = null;
  export let initialUserId: number | null = null;
  export let onSectionChange: (section: string, userId?: number) => void = () => {};
  export let onSettingsSaved: (payload: SettingsSavedPayload) => void | Promise<void> = () => {};
  export let onTariffsSaved: (catalog: TariffsCatalog) => void | Promise<void> = () => {};
  export let onThemesSaved: () => void | Promise<void> = () => {};
  export let onTranslationsSaved: (
    payload: TranslationsSavedPayload
  ) => void | Promise<void> = () => {};
  export let routePrefix = "";
  export let brand: Record<string, unknown> = {};
  export let brandTitle = "Subscription";
  export let appFaviconUrl = "";
  export let appFaviconUseCustom = false;
  export let appVersion = "dev+local";
  export let appRepositoryUrl = "https://minishop.minidoc.cc/";
  export let currentLang = "ru";
  export let languageOptions: LanguageOption[] = [];
  export let languageBusy = false;
  export let onLanguageChange: (value: string, meta: LanguageChangeMeta) => void = () => {};
  export let t: TranslateFn = (key, _params = {}, fallback = "") => fallback || key;

  const at: TranslateFn = (key, params = {}, fallback = "") =>
    t(`admin_${key}`, params, fallback || key);

  let featureSet = new Set<string>();
  let visibleSections: AdminSectionDescriptor[] = [];
  let NAV_GROUPS: NavGroup[] = [];
  let SECTION_META: Record<string, SectionMeta> = {};
  let SECTION_BY_ID = new Map<string, AdminSectionDescriptor>();
  let VALID_SECTIONS: string[] = [];

  $: featureSet = new Set<string>(($settingsStore?.features || []) as string[]);
  $: visibleSections = ADMIN_SECTIONS.filter(
    (section) => !section.feature || featureSet.has(section.feature)
  );
  $: NAV_GROUPS = ADMIN_SECTION_GROUPS.map((group) => ({
    id: group.id,
    order: group.order,
    label: at(group.i18nKey, {}, group.fallbackLabel),
    items: visibleSections
      .filter((section) => section.group === group.id)
      .sort((a, b) => a.order - b.order || a.id.localeCompare(b.id))
      .map((section) => ({
        ...section,
        label: at(section.i18nKey, {}, section.fallbackLabel),
      })),
  })).filter((group) => group.items.length);
  $: SECTION_META = Object.fromEntries(
    visibleSections.map((section) => [
      section.id,
      {
        title: at(section.titleI18nKey, {}, section.fallbackTitle),
        subtitle: at(section.subtitleI18nKey, {}, section.fallbackSubtitle),
      },
    ])
  );
  $: SECTION_BY_ID = new Map(visibleSections.map((section) => [section.id, section]));

  $: VALID_SECTIONS = (NAV_GROUPS || []).flatMap((group) =>
    (group.items || []).map((item) => item.id)
  );
  const normalizeSection = (value: unknown): AdminSectionId =>
    (VALID_SECTIONS || []).includes(String(value)) ? String(value) : "stats";
  const settingsPathKey = (path: unknown): string => (Array.isArray(path) ? path : []).join("/");

  let active = normalizeSection(initialSection);
  let lastInitialSection = active;
  $: if (VALID_SECTIONS.length && !VALID_SECTIONS.includes(active)) {
    active = normalizeSection(active);
  }
  let settingsPath: SettingsPath = Array.isArray(initialSettingsPath) ? initialSettingsPath : [];
  let lastInitialSettingsPathKey = settingsPathKey(settingsPath);
  $: {
    const nextInitialSection = normalizeSection(initialSection);
    if (nextInitialSection !== lastInitialSection) {
      active = nextInitialSection;
      lastInitialSection = nextInitialSection;
    }
  }
  $: {
    const nextInitialSettingsPathKey = settingsPathKey(initialSettingsPath);
    if (nextInitialSettingsPathKey !== lastInitialSettingsPathKey) {
      settingsPath = Array.isArray(initialSettingsPath) ? initialSettingsPath : [];
      lastInitialSettingsPathKey = nextInitialSettingsPathKey;
    }
  }
  let sidebarOpen = false;
  let isCompact = false;
  let dismissedUserRouteKey = "";
  let lastUserRouteKey = "";
  let adminLanguageMenuOpen = false;
  let adminLanguageClickGuard = false;
  let adminLanguageClickGuardArmed = false;
  let adminLanguageClickGuardTimer: ReturnType<typeof window.setTimeout> | null = null;
  let adminLanguageClickGuardArmTimer: ReturnType<typeof window.setTimeout> | null = null;
  $: adminLanguageGuardActive = isCompact && (adminLanguageMenuOpen || adminLanguageClickGuard);

  function readReduceMotion() {
    return (
      typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  let reduceMotion = readReduceMotion();

  function flash(text: string): void {
    onToast(text);
  }

  function dynamicComponent(component: unknown): DynamicComponent {
    return component as DynamicComponent;
  }

  const adminQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        gcTime: 10 * 60 * 1000,
        retry: false,
        staleTime: 60 * 1000,
      },
    },
  });

  const adsStore = createAdsStore({ api, onToast: flash, at });
  const backupsStore = createBackupsStore({ api, onToast: flash, at });
  const broadcastStore = createBroadcastStore({ api, onToast: flash, at });
  const healthStore = createHealthStore({ api, at, queryClient: adminQueryClient });
  const logsStore = createLogsStore({ api, onToast: flash, at, queryClient: adminQueryClient });
  const paymentsStore = createPaymentsStore({ api, onToast: flash, at, routePrefix });
  const promosStore = createPromosStore({ api, onToast: flash, at });
  const settingsStore = createSettingsStore({ api, onToast: flash, at });
  const statsStore = createStatsStore({ api, onToast: flash, at });
  const supportStore = createAdminSupportStore({ api, onToast: flash, at, routePrefix });
  const tariffsStore = createTariffsStore({ api, onTariffsSaved, flash, at });
  const themesStore = createThemesStore({ api, onThemesSaved, flash, at });
  const translationsStore = createTranslationsStore({ api, onToast: flash, at });
  const usersStore = createUsersStore({ api, onToast: flash, at, routePrefix });

  setContext("promosStore", promosStore);
  setContext("adsStore", adsStore);
  setContext("healthStore", healthStore);
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
  $: activeSection = SECTION_BY_ID.get(active);
  $: openSectionUserCard =
    active === "payments"
      ? openPaymentUserCard
      : active === "logs"
        ? openLogsUserCard
        : openUserCard;
  $: currentLanguageOption =
    languageOptions.find((option) => option.value === currentLang) || languageOptions[0];

  const gravatarCache = createGravatarCache(() => usersStore.updateState({}));

  function setActive(id: string): void {
    const next = normalizeSection(id);
    sidebarOpen = false;
    if (active === next) return;
    active = next;
    settingsPath = [];
    usersStore.closeUser();
    paymentsStore.closePayment();
    supportStore.closeTicketView();
    onSectionChange(next);
  }

  function openSettingsPath(path: unknown = []): void {
    const nextPath = (Array.isArray(path) ? path : [])
      .map((segment) => String(segment || "").trim())
      .filter(Boolean)
      .slice(0, 3);
    const next = normalizeSection("settings");
    sidebarOpen = false;
    active = next;
    settingsPath = nextPath;
    usersStore.closeUser();
    paymentsStore.closePayment();
    supportStore.closeTicketView();
    if (typeof window !== "undefined" && window.location.protocol !== "file:") {
      const pathSuffix = nextPath.length ? `/${nextPath.map(encodeURIComponent).join("/")}` : "";
      const targetPath = withRoutePrefix(`/admin/settings${pathSuffix}`, routePrefix);
      const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
      if (
        `${window.location.pathname}${window.location.search}${window.location.hash}` !== nextUrl
      ) {
        window.history.pushState(null, "", nextUrl);
      }
    }
    onSectionChange(next);
  }

  function changeLanguage(value: string): void {
    adminLanguageMenuOpen = false;
    clearAdminLanguageClickGuard();
    onLanguageChange(value, { section: "admin", adminSection: active });
  }

  function currentRoutePathname(): string {
    if (typeof window === "undefined") return "/";
    return stripRoutePrefix(window.location.pathname, routePrefix);
  }

  function readSectionFromPath(): AdminSectionId {
    if (typeof window === "undefined") return "stats";
    const match = currentRoutePathname().match(/^\/admin\/([a-z0-9_-]+)(?:\/.*)?$/i);
    return normalizeSection(match ? match[1].toLowerCase() : "stats");
  }

  function readSettingsPathFromPath(): SettingsPath {
    if (typeof window === "undefined") return [];
    return adminSettingsPathFromPath(currentRoutePathname());
  }

  function readUserIdFromPath(): number | null {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/users\/(-?\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function readSupportTicketIdFromPath(): number | null {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/support\/(\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function readPaymentIdFromPath(): number | null {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/payments\/(\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function readPaymentUserIdFromPath(): number | null {
    if (typeof window === "undefined") return null;
    const match = currentRoutePathname().match(/^\/admin\/payments\/users\/(-?\d+)$/);
    return match ? Number(match[1]) : null;
  }

  function onPopState(): void {
    active = readSectionFromPath();
    settingsPath = active === "settings" ? readSettingsPathFromPath() : [];
    sidebarOpen = false;
    const userId = readUserIdFromPath();
    const paymentUserId = active === "payments" ? readPaymentUserIdFromPath() : null;
    const contextualUserId = paymentUserId || userId;
    if (contextualUserId) {
      if (!$usersStore.openedUser || $usersStore.openedUser.user_id !== contextualUserId) {
        void usersStore.openUser(contextualUserId, {
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
        void paymentsStore.openPayment(paymentId, { skipPush: true });
      }
    } else if ($paymentsStore.openedPaymentId) {
      paymentsStore.closePayment({ skipPush: true });
    }
    const ticketId = readSupportTicketIdFromPath();
    if (active === "support" && ticketId) {
      if (!$supportStore.openedTicketId || $supportStore.openedTicketId !== ticketId) {
        void supportStore.openTicket(ticketId, { skipPush: true });
      }
    } else if (active === "support" && $supportStore.openedTicketId) {
      supportStore.closeTicketView({ skipPush: true });
    }
  }

  function exportPayments(): void {
    if (typeof window === "undefined") return;
    window.open("/api/admin/payments/export.csv", "_blank", "noopener");
  }

  function openPaymentUserCard(userId: unknown): void {
    const uid = Number(userId);
    // Synthetic email-only users use negative user_id; still a valid admin target.
    if (!Number.isFinite(uid) || uid === 0) return;
    dismissedUserRouteKey = "";
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
    void usersStore.openUser(uid, { pathContext: "payments" });
  }

  function openLogsUserCard(userId: unknown): void {
    const uid = Number(userId);
    if (!Number.isFinite(uid) || uid === 0) return;
    dismissedUserRouteKey = "";
    const next = normalizeSection("logs");
    sidebarOpen = false;
    if (active !== next) {
      active = next;
      paymentsStore.closePayment({ skipPush: true });
      supportStore.closeTicketView({ skipPush: true });
      onSectionChange(next);
    }
    usersStore.setActive(next);
    void usersStore.openUser(uid, { skipPush: true });
  }

  function openUserCard(userId: unknown): void {
    const uid = Number(userId);
    if (!Number.isFinite(uid) || uid === 0) return;
    dismissedUserRouteKey = "";
    sidebarOpen = false;
    usersStore.setActive(active);
    void usersStore.openUser(uid, {
      skipPush: true,
      pathContext: active === "users" || active === "payments" ? active : undefined,
    });
  }

  function userRouteKey(section = active): string {
    if (section === "users" && initialUserId) return `users:${initialUserId}`;
    if (section === "payments" && initialPaymentUserId) return `payments:${initialPaymentUserId}`;
    return "";
  }

  function closeUserCard(): void {
    dismissedUserRouteKey = userRouteKey();
    usersStore.closeUser({ skipPush: true });
    if (active === "users" || active === "payments") {
      onSectionChange(active, 0);
    }
  }

  function resolvedAvatarUrl(user: AdminUser | null | undefined): string {
    return userAvatarUrl(user) || (user?.email ? gravatarCache.gravatarUrl(user.email) : "");
  }

  function panelStatusBadge(user: AdminUser | null | undefined): PanelStatusBadge {
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

  let compactMql: MediaQueryList | null = null;
  function onCompactChange(event: MediaQueryListEvent | MediaQueryList): void {
    isCompact = Boolean(event?.matches);
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

  onMount(() => {
    adminQueryClient.mount();
    reduceMotion = readReduceMotion();
    let motionMql: MediaQueryList | null = null;
    const onMotionChange = (): void => {
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
    void healthStore.loadHealth();
    // Feature flags arrive with the settings manifest; without this eager
    // load, feature-gated sections stay hidden until the admin happens to
    // open a section that fetches settings on its own.
    void settingsStore.loadSettings();
    const healthTimer: ReturnType<typeof window.setInterval> | null =
      typeof window !== "undefined"
        ? window.setInterval(() => void healthStore.loadHealth(), 5 * 60 * 1000)
        : null;
    return () => {
      if (motionMql) motionMql.removeEventListener("change", onMotionChange);
      if (compactMql) {
        if (compactMql.removeEventListener)
          compactMql.removeEventListener("change", onCompactChange);
        else if (compactMql.removeListener) compactMql.removeListener(onCompactChange);
      }
      if (typeof window !== "undefined") window.removeEventListener("popstate", onPopState);
      if (healthTimer !== null) window.clearInterval(healthTimer);
      adminQueryClient.unmount();
      clearAdminLanguageClickGuard();
    };
  });

  $: sectionFade = reduceMotion ? { duration: 0 } : { duration: 200 };
  $: sidebarBackdropFade = reduceMotion ? { duration: 0 } : { duration: 180 };

  $: {
    const currentUserRouteKey = userRouteKey();
    if (currentUserRouteKey !== lastUserRouteKey) {
      if (currentUserRouteKey !== dismissedUserRouteKey) dismissedUserRouteKey = "";
      lastUserRouteKey = currentUserRouteKey;
    }
  }

  $: if (
    active === "users" &&
    initialUserId &&
    dismissedUserRouteKey !== `users:${initialUserId}` &&
    (!$usersStore.openedUser || $usersStore.openedUser.user_id !== initialUserId)
  ) {
    void usersStore.openUser(initialUserId, { skipPush: true });
  }

  $: if (
    active === "payments" &&
    initialPaymentId &&
    (!$paymentsStore.openedPaymentId || $paymentsStore.openedPaymentId !== initialPaymentId)
  ) {
    void paymentsStore.openPayment(initialPaymentId, { skipPush: true });
  }

  $: if (
    active === "payments" &&
    initialPaymentUserId &&
    dismissedUserRouteKey !== `payments:${initialPaymentUserId}` &&
    (!$usersStore.openedUser || $usersStore.openedUser.user_id !== initialPaymentUserId)
  ) {
    void usersStore.openUser(initialPaymentUserId, { skipPush: true, pathContext: "payments" });
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
            <svelte:component this={dynamicComponent(item.icon)} size={16} />
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
      <ConfigAlertsBanner {at} section={active} onNavigate={setActive} />
      {#key active}
        <div class="admin-section-stage" in:fade={sectionFade} out:fade={sectionFade}>
          {#if activeSection}
            <svelte:component
              this={dynamicComponent(activeSection.component)}
              {at}
              {brand}
              {currentLang}
              {fmtDate}
              {fmtDateShort}
              {fmtMoney}
              {onSettingsSaved}
              {onTranslationsSaved}
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
              onOpenUserCard={openSectionUserCard}
              onOpenSettingsPath={openSettingsPath}
              onSettingsPathChange={(path: SettingsPath) => (settingsPath = path)}
              initialTicketId={readSupportTicketIdFromPath()}
            />
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
  onClose={closeUserCard}
/>
