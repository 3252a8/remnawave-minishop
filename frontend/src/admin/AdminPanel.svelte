<script lang="ts">
  import { QueryClient } from "@tanstack/svelte-query";
  import { ArrowLeft, Check, ChevronsUpDown, Globe2, Menu } from "$components/ui/icons.js";
  import { onMount } from "svelte";
  import { MediaQuery } from "svelte/reactivity";
  import { prefersReducedMotion } from "svelte/motion";
  import { fade } from "svelte/transition";
  import { Select } from "$components/ui/primitives.js";
  import { AdminBadge, AdminButton } from "$components/patterns/admin/index.js";

  import BrandMark from "$lib/webapp/BrandMark.svelte";
  import AdminHeaderActions from "./AdminHeaderActions.svelte";
  import AdminLazyModals from "./AdminLazyModals.svelte";
  import { ADMIN_SECTION_GROUPS, ADMIN_SECTIONS } from "./sections/registry";
  import ConfigAlertsBanner from "./ConfigAlertsBanner.svelte";
  import {
    createAdminSectionComponentLoader,
    dynamicComponent,
    type DynamicComponent,
  } from "./adminLazyComponents";
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
    paymentStatusLabel as formatPaymentStatusLabel,
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
  import { buildAdminPaymentsExportPath } from "../lib/webapp/publicApi";
  import {
    setAdsStore,
    setAdminSupportStore,
    setBackupsStore,
    setBroadcastStore,
    setHealthStore,
    setLogsStore,
    setPaymentsStore,
    setPromosStore,
    setSettingsStore,
    setStatsStore,
    setTariffsStore,
    setThemesStore,
    setTranslationsStore,
    setUsersStore,
  } from "../lib/admin/context";
  import type { AdminSectionDescriptor } from "./sections/registry";
  import type { SettingsSavedPayload } from "../lib/admin/stores/settingsStore";
  import type { TariffsCatalog } from "../lib/admin/stores/tariffsStore";
  import type { TranslationsSavedPayload } from "../lib/admin/stores/translationsStore";
  import type { AdminUser } from "../lib/admin/stores/usersStore";

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

  let {
    api,
    onClose = () => {},
    onToast = () => {},
    initialSection = "stats",
    initialSettingsPath = [],
    initialPaymentId = null,
    initialPaymentUserId = null,
    initialUserId = null,
    onSectionChange = () => {},
    onSettingsSaved = () => {},
    onTariffsSaved = () => {},
    onThemesSaved = () => {},
    onTranslationsSaved = () => {},
    routePrefix = "",
    brand = {},
    brandTitle = "Subscription",
    appFaviconUrl = "",
    appFaviconUseCustom = false,
    appVersion = "dev+local",
    appRepositoryUrl = "https://minishop.minidoc.cc/",
    currentLang = "ru",
    languageOptions = [],
    languageBusy = false,
    onLanguageChange = () => {},
    t = (key, _params = {}, fallback = "") => fallback || key,
  }: {
    api: AdminApi;
    onClose?: () => void;
    onToast?: (message: string) => void;
    initialSection?: string;
    initialSettingsPath?: SettingsPath;
    initialPaymentId?: number | null;
    initialPaymentUserId?: number | null;
    initialUserId?: number | null;
    onSectionChange?: (section: string, userId?: number) => void;
    onSettingsSaved?: (payload: SettingsSavedPayload) => void | Promise<void>;
    onTariffsSaved?: (catalog: TariffsCatalog) => void | Promise<void>;
    onThemesSaved?: () => void | Promise<void>;
    onTranslationsSaved?: (payload: TranslationsSavedPayload) => void | Promise<void>;
    routePrefix?: string;
    brand?: Record<string, unknown>;
    brandTitle?: string;
    appFaviconUrl?: string;
    appFaviconUseCustom?: boolean;
    appVersion?: string;
    appRepositoryUrl?: string;
    currentLang?: string;
    languageOptions?: LanguageOption[];
    languageBusy?: boolean;
    onLanguageChange?: (value: string, meta: LanguageChangeMeta) => void;
    t?: TranslateFn;
  } = $props();

  const at: TranslateFn = (key, params = {}, fallback = "") =>
    t(`admin_${key}`, params, fallback || key);
  const paymentStatusLabel = (status: unknown): string => formatPaymentStatusLabel(status, at);

  function initialApi(): AdminApi {
    return api;
  }

  function initialRoutePrefix(): string {
    return routePrefix;
  }

  function initialTariffsSaved(): (catalog: TariffsCatalog) => void | Promise<void> {
    return onTariffsSaved;
  }

  function initialThemesSaved(): () => void | Promise<void> {
    return onThemesSaved;
  }

  const stableApi = initialApi();
  const stableRoutePrefix = initialRoutePrefix();
  const stableOnTariffsSaved = initialTariffsSaved();
  const stableOnThemesSaved = initialThemesSaved();
  const settingsStore = createSettingsStore({ api: stableApi, onToast: flash, at });

  const featureSet = $derived(new Set<string>((settingsStore.features || []) as string[]));
  const visibleSections: AdminSectionDescriptor[] = $derived(
    ADMIN_SECTIONS.filter((section) => !section.feature || featureSet.has(section.feature))
  );
  const NAV_GROUPS: NavGroup[] = $derived(
    ADMIN_SECTION_GROUPS.map((group) => ({
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
    })).filter((group) => group.items.length)
  );
  const SECTION_META: Record<string, SectionMeta> = $derived(
    Object.fromEntries(
      visibleSections.map((section) => [
        section.id,
        {
          title: at(section.titleI18nKey, {}, section.fallbackTitle),
          subtitle: at(section.subtitleI18nKey, {}, section.fallbackSubtitle),
        },
      ])
    )
  );
  const SECTION_BY_ID = $derived(new Map(visibleSections.map((section) => [section.id, section])));

  const VALID_SECTIONS: string[] = $derived(
    (NAV_GROUPS || []).flatMap((group) => (group.items || []).map((item) => item.id))
  );
  const normalizeSection = (value: unknown): AdminSectionId =>
    (VALID_SECTIONS || []).includes(String(value)) ? String(value) : "stats";
  const settingsPathKey = (path: unknown): string => (Array.isArray(path) ? path : []).join("/");

  function initialActiveSection(): AdminSectionId {
    return normalizeSection(initialSection);
  }

  function initialSettingsPathValue(): SettingsPath {
    return Array.isArray(initialSettingsPath) ? initialSettingsPath : [];
  }

  const initialActive = initialActiveSection();
  const initialSettingsPathSnapshot = initialSettingsPathValue();
  let active = $state(initialActive);
  let lastInitialSection = $state(initialActive);
  let settingsPath = $state<SettingsPath>(initialSettingsPathSnapshot);
  let lastInitialSettingsPathKey = $state(settingsPathKey(initialSettingsPathSnapshot));

  $effect(() => {
    if (VALID_SECTIONS.length && !VALID_SECTIONS.includes(active)) {
      active = normalizeSection(active);
    }
  });

  $effect(() => {
    const nextInitialSection = normalizeSection(initialSection);
    if (nextInitialSection !== lastInitialSection) {
      active = nextInitialSection;
      lastInitialSection = nextInitialSection;
    }
  });

  $effect(() => {
    const nextInitialSettingsPathKey = settingsPathKey(initialSettingsPath);
    if (nextInitialSettingsPathKey !== lastInitialSettingsPathKey) {
      settingsPath = Array.isArray(initialSettingsPath) ? initialSettingsPath : [];
      lastInitialSettingsPathKey = nextInitialSettingsPathKey;
    }
  });

  const compactQuery = new MediaQuery("max-width: 720px", false);
  let sidebarOpen = $state(false);
  const isCompact = $derived(compactQuery.current);
  let dismissedUserRouteKey = $state("");
  let lastUserRouteKey = $state("");
  let adminLanguageMenuOpen = $state(false);
  let adminLanguageClickGuard = $state(false);
  let adminLanguageClickGuardArmed = $state(false);
  let adminLanguageClickGuardTimer: ReturnType<typeof window.setTimeout> | null = null;
  let adminLanguageClickGuardArmTimer: ReturnType<typeof window.setTimeout> | null = null;
  const adminLanguageGuardActive = $derived(
    isCompact && (adminLanguageMenuOpen || adminLanguageClickGuard)
  );

  function flash(text: string): void {
    onToast(text);
  }

  function sectionFade() {
    return { duration: prefersReducedMotion.current ? 0 : 200 };
  }

  function sidebarBackdropFade() {
    return { duration: prefersReducedMotion.current ? 0 : 180 };
  }

  const sectionComponentLoader = createAdminSectionComponentLoader();
  let sectionLoadToken = 0;
  let activeSectionComponent = $state<DynamicComponent | null>(null);
  let activeSectionLoading = $state(false);

  function warmSectionComponent(section: AdminSectionDescriptor): void {
    sectionComponentLoader.warm(section);
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

  const adsStore = createAdsStore({ api: stableApi, onToast: flash, at });
  const backupsStore = createBackupsStore({ api: stableApi, onToast: flash, at });
  const broadcastStore = createBroadcastStore({ api: stableApi, onToast: flash, at });
  const healthStore = createHealthStore({ api: stableApi, at, queryClient: adminQueryClient });
  const logsStore = createLogsStore({
    api: stableApi,
    onToast: flash,
    at,
    queryClient: adminQueryClient,
  });
  const paymentsStore = createPaymentsStore({
    api: stableApi,
    onToast: flash,
    at,
    routePrefix: stableRoutePrefix,
    queryClient: adminQueryClient,
  });
  const promosStore = createPromosStore({
    api: stableApi,
    onToast: flash,
    at,
    queryClient: adminQueryClient,
  });
  const statsStore = createStatsStore({
    api: stableApi,
    onToast: flash,
    at,
    queryClient: adminQueryClient,
  });
  const supportStore = createAdminSupportStore({
    api: stableApi,
    onToast: flash,
    at,
    routePrefix: stableRoutePrefix,
  });
  const tariffsStore = createTariffsStore({
    api: stableApi,
    onTariffsSaved: stableOnTariffsSaved,
    flash,
    at,
  });
  const themesStore = createThemesStore({
    api: stableApi,
    onThemesSaved: stableOnThemesSaved,
    flash,
    at,
  });
  const translationsStore = createTranslationsStore({ api: stableApi, onToast: flash, at });
  const usersStore = createUsersStore({
    api: stableApi,
    onToast: flash,
    at,
    routePrefix: stableRoutePrefix,
    queryClient: adminQueryClient,
  });

  setPromosStore(promosStore);
  setAdsStore(adsStore);
  setHealthStore(healthStore);
  setBackupsStore(backupsStore);
  setBroadcastStore(broadcastStore);
  setLogsStore(logsStore);
  setPaymentsStore(paymentsStore);
  setStatsStore(statsStore);
  setAdminSupportStore(supportStore);
  setSettingsStore(settingsStore);
  setUsersStore(usersStore);
  setTariffsStore(tariffsStore);
  setThemesStore(themesStore);
  setTranslationsStore(translationsStore);

  $effect(() => {
    usersStore.setActive(active);
    paymentsStore.setActive(active);
    supportStore.setActive(active);
  });

  const dirtyCount = $derived(Object.keys(settingsStore.settingsDirty || {}).length);
  const translationsDirtyCount = $derived(
    Object.keys(translationsStore.translationsDirty || {}).length
  );
  const syncBusy = $derived(statsStore.syncBusy);
  const settingsSaving = $derived(settingsStore.settingsSaving);
  const translationsSaving = $derived(translationsStore.translationsSaving);
  const meta = $derived(SECTION_META[active] || { title: active, subtitle: "" });
  const activeSection = $derived(SECTION_BY_ID.get(active));
  const openSectionUserCard = $derived(
    active === "payments"
      ? openPaymentUserCard
      : active === "logs"
        ? openLogsUserCard
        : openUserCard
  );
  const currentLanguageOption = $derived(
    languageOptions.find((option) => option.value === currentLang) || languageOptions[0]
  );

  const gravatarCache = createGravatarCache(() => usersStore.updateState({}));

  $effect(() => {
    const section = activeSection;
    const token = ++sectionLoadToken;
    activeSectionComponent = null;
    if (!section) {
      activeSectionLoading = false;
      return;
    }
    activeSectionLoading = true;
    void sectionComponentLoader
      .load(section)
      .then((component) => {
        if (token !== sectionLoadToken) return;
        activeSectionComponent = component;
      })
      .catch((error: unknown) => {
        if (token !== sectionLoadToken) return;
        flash(error instanceof Error ? error.message : String(error || "section_load_failed"));
      })
      .finally(() => {
        if (token === sectionLoadToken) activeSectionLoading = false;
      });
  });

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
      if (!usersStore.openedUser || usersStore.openedUser.user_id !== contextualUserId) {
        void usersStore.openUser(contextualUserId, {
          skipPush: true,
          pathContext: paymentUserId ? "payments" : "users",
        });
      }
    } else if (usersStore.openedUser) {
      usersStore.closeUser({ skipPush: true });
    }
    const paymentId = readPaymentIdFromPath();
    if (active === "payments" && paymentId) {
      if (!paymentsStore.openedPaymentId || paymentsStore.openedPaymentId !== paymentId) {
        void paymentsStore.openPayment(paymentId, { skipPush: true });
      }
    } else if (paymentsStore.openedPaymentId) {
      paymentsStore.closePayment({ skipPush: true });
    }
    const ticketId = readSupportTicketIdFromPath();
    if (active === "support" && ticketId) {
      if (!supportStore.openedTicketId || supportStore.openedTicketId !== ticketId) {
        void supportStore.openTicket(ticketId, { skipPush: true });
      }
    } else if (active === "support" && supportStore.openedTicketId) {
      supportStore.closeTicketView({ skipPush: true });
    }
  }

  function exportPayments(): void {
    if (typeof window === "undefined") return;
    window.open(buildAdminPaymentsExportPath(), "_blank", "noopener");
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
      case "inactive_user_not_found":
      case "panel_user_not_found":
        return {
          label: at("status_panel_user_not_found", {}, "Panel user not found"),
          variant: "muted",
        };
      case "cancelled":
      case "canceled":
        return { label: at("status_cancelled", {}, "Canceled"), variant: "muted" };
      case "trial":
        return { label: at("status_trial", {}, "Trial"), variant: "success" };
      default:
        return {
          label: status ? at("status_unknown_panel", {}, "Unknown panel status") : "—",
          variant: "muted",
        };
    }
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
      if (typeof window !== "undefined") window.removeEventListener("popstate", onPopState);
      if (healthTimer !== null) window.clearInterval(healthTimer);
      adminQueryClient.unmount();
      clearAdminLanguageClickGuard();
    };
  });

  $effect(() => {
    const currentUserRouteKey = userRouteKey();
    if (currentUserRouteKey !== lastUserRouteKey) {
      if (currentUserRouteKey !== dismissedUserRouteKey) dismissedUserRouteKey = "";
      lastUserRouteKey = currentUserRouteKey;
    }
  });

  $effect(() => {
    if (
      active === "users" &&
      initialUserId &&
      dismissedUserRouteKey !== `users:${initialUserId}` &&
      (!usersStore.openedUser || usersStore.openedUser.user_id !== initialUserId)
    ) {
      void usersStore.openUser(initialUserId, { skipPush: true });
    }
  });

  $effect(() => {
    if (
      active === "payments" &&
      initialPaymentId &&
      (!paymentsStore.openedPaymentId || paymentsStore.openedPaymentId !== initialPaymentId)
    ) {
      void paymentsStore.openPayment(initialPaymentId, { skipPush: true });
    }
  });

  $effect(() => {
    if (
      active === "payments" &&
      initialPaymentUserId &&
      dismissedUserRouteKey !== `payments:${initialPaymentUserId}` &&
      (!usersStore.openedUser || usersStore.openedUser.user_id !== initialPaymentUserId)
    ) {
      void usersStore.openUser(initialPaymentUserId, { skipPush: true, pathContext: "payments" });
    }
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
      aria-label={at("close_menu", {}, "Закрыть меню")}
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
      aria-label={t("wa_close", {}, at("close", {}, "Закрыть"))}
      onpointerdown={closeAdminLanguageFromGuard}
      onclick={closeAdminLanguageFromGuard}
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
          {@const NavIcon = dynamicComponent(item.icon)}
          <button
            type="button"
            class="admin-nav-item"
            class:active={active === item.id}
            data-admin-section={item.id}
            onfocus={() => warmSectionComponent(item)}
            onpointerenter={() => warmSectionComponent(item)}
            onclick={() => setActive(item.id)}
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
          onclick={() => (sidebarOpen = !sidebarOpen)}
          aria-label={at("menu", {}, "Меню")}
        >
          <Menu size={18} />
        </button>
        <div class="admin-header-title">
          <h2>{meta.title}</h2>
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
        onExportPayments={exportPayments}
        onSaveSettings={() => settingsStore.saveSettings(onSettingsSaved)}
        onSaveTranslations={() => translationsStore.saveTranslations(onTranslationsSaved)}
        onSyncStats={statsStore.triggerSync}
      />
    </header>

    <main class="admin-main">
      <ConfigAlertsBanner {at} section={active} onNavigate={setActive} />
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
              {brand}
              {currentLang}
              {fmtDate}
              {fmtDateShort}
              {fmtMoney}
              {onSettingsSaved}
              {onTranslationsSaved}
              {paymentStatusLabel}
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
  {paymentStatusLabel}
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
  onCloseUser={closeUserCard}
  onOpenPaymentUserCard={openPaymentUserCard}
/>
