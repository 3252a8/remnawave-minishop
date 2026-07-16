<script lang="ts">
  import { onMount } from "svelte";

  import AdminPanelLayout from "./AdminPanelLayout.svelte";
  import { ADMIN_SECTION_GROUPS, ADMIN_SECTIONS, isAdminSectionVisible } from "./sections/registry";
  import { createAdminSectionComponentLoader, type DynamicComponent } from "./adminLazyComponents";
  import { createAdminStores, type AdminApi } from "./adminStores";
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
  import { buildAdminPaymentsExportPath } from "../lib/webapp/publicApi";
  import type { AdminSectionDescriptor } from "./sections/registry";
  import type { SettingsSavedPayload } from "../lib/admin/stores/settingsStore";
  import type { TariffsCatalog } from "../lib/admin/stores/tariffsStore";
  import type { TranslationsSavedPayload } from "../lib/admin/stores/translationsStore";
  import type { AdminUser } from "../lib/admin/stores/usersStore";

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
  const {
    adminQueryClient,
    adsStore,
    healthStore,
    paymentsStore,
    promosStore,
    settingsStore,
    statsStore,
    supportStore,
    tariffsStore,
    translationsStore,
    usersStore,
  } = createAdminStores({
    api: stableApi,
    onToast: flash,
    at,
    routePrefix: stableRoutePrefix,
    onTariffsSaved: stableOnTariffsSaved,
    onThemesSaved: stableOnThemesSaved,
  });

  const featureSet = $derived(new Set<string>((settingsStore.features || []) as string[]));
  const visibleSections: AdminSectionDescriptor[] = $derived(
    ADMIN_SECTIONS.filter((section) => isAdminSectionVisible(section, featureSet))
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

  let sidebarOpen = $state(false);
  let dismissedUserRouteKey = $state("");
  let lastUserRouteKey = $state("");

  function flash(text: string): void {
    onToast(text);
  }

  const sectionComponentLoader = createAdminSectionComponentLoader();
  let sectionLoadToken = 0;
  let activeSectionComponent = $state<DynamicComponent | null>(null);
  let activeSectionLoading = $state(false);

  function warmSectionComponent(section: AdminSectionDescriptor): void {
    sectionComponentLoader.warm(section);
  }

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
    if (user?.is_banned) return { label: at("status_banned", {}, "Banned"), variant: "danger" };
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
        return { label: at("status_bot_only", {}, "Bot Only"), variant: "muted" };
      default:
        return { label: status || "—", variant: "muted" };
    }
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

<AdminPanelLayout
  {active}
  {activeSectionComponent}
  {activeSectionLoading}
  {adsStore}
  {appFaviconUrl}
  {appFaviconUseCustom}
  {appRepositoryUrl}
  {appVersion}
  {at}
  {brand}
  {brandTitle}
  {currentLang}
  {dirtyCount}
  {fmtDate}
  {fmtDateShort}
  {fmtMoney}
  initialTicketId={readSupportTicketIdFromPath()}
  {languageBusy}
  {languageOptions}
  {meta}
  {NAV_GROUPS}
  {onClose}
  {onLanguageChange}
  onCloseUser={closeUserCard}
  onExportPayments={exportPayments}
  onOpenPaymentUserCard={openPaymentUserCard}
  onOpenSettingsPath={openSettingsPath}
  onOpenUserCard={openSectionUserCard}
  onSaveSettings={onSettingsSaved}
  onSaveTranslations={onTranslationsSaved}
  onSetActive={setActive}
  onSettingsPathChange={(path: SettingsPath) => (settingsPath = path)}
  {openTelegramProfileLink}
  {paymentStatusVariant}
  {panelStatusBadge}
  {promosStore}
  {resolvedAvatarUrl}
  {routePrefix}
  {settingsPath}
  {settingsSaving}
  {settingsStore}
  bind:sidebarOpen
  {statsStore}
  {supportStore}
  {syncBusy}
  {tariffsStore}
  {translationsDirtyCount}
  {translationsSaving}
  {translationsStore}
  {trafficLeftLabel}
  {trafficOfLabel}
  {trafficPercentValue}
  {userDisplayName}
  {userInitials}
  {userSecondaryName}
  {userTelegramProfileLink}
  {userTelegramProfileLinkKind}
  {warmSectionComponent}
  {t}
/>
