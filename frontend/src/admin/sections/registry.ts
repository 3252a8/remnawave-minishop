import {
  Coins,
  CreditCard,
  Database,
  FileText,
  Languages,
  LayoutDashboard,
  LifeBuoy,
  Megaphone,
  Paintbrush,
  Sliders,
  Sparkles,
  Tag,
  UsersRound,
} from "$components/ui/icons.js";

export interface AdminSectionDescriptor {
  id: string;
  group: string;
  order: number;
  i18nKey: string;
  fallbackLabel: string;
  titleI18nKey: string;
  fallbackTitle: string;
  subtitleI18nKey: string;
  fallbackSubtitle: string;
  icon: unknown;
  component?: unknown;
  loadComponent?: () => Promise<unknown>;
  /** @deprecated Prefer requiredFeature for new extension descriptors. */
  feature?: string;
  /** Feature required to use this extension section. Navigation-only metadata. */
  requiredFeature?: string;
  /** Keep a feature-locked extension discoverable so it can render its own locked state. */
  visibleWhenLocked?: boolean;
}

export function requiredFeatureForAdminSection(section: AdminSectionDescriptor): string {
  return String(section.requiredFeature || section.feature || "").trim();
}

export function isAdminSectionVisible(
  section: AdminSectionDescriptor,
  availableFeatures: ReadonlySet<string>
): boolean {
  const requiredFeature = requiredFeatureForAdminSection(section);
  return (
    !requiredFeature || availableFeatures.has(requiredFeature) || Boolean(section.visibleWhenLocked)
  );
}

export const ADMIN_SECTION_GROUPS = [
  { id: "overview", order: 10, i18nKey: "nav_overview", fallbackLabel: "Overview" },
  { id: "operations", order: 20, i18nKey: "nav_operations", fallbackLabel: "Operations" },
  {
    id: "communication",
    order: 30,
    i18nKey: "nav_communication",
    fallbackLabel: "Communication",
  },
  { id: "system", order: 40, i18nKey: "nav_system", fallbackLabel: "System" },
];

const CORE_ADMIN_SECTIONS: AdminSectionDescriptor[] = [
  {
    id: "stats",
    group: "overview",
    order: 10,
    i18nKey: "nav_dashboard",
    fallbackLabel: "Dashboard",
    titleI18nKey: "section_stats_title",
    fallbackTitle: "Dashboard",
    subtitleI18nKey: "section_stats_subtitle",
    fallbackSubtitle: "Audience, revenue, Remnawave panel, and recent payments",
    icon: LayoutDashboard,
    loadComponent: () => import("./StatsSection.svelte").then((module) => module.default),
  },
  {
    id: "users",
    group: "operations",
    order: 10,
    i18nKey: "nav_users",
    fallbackLabel: "Users",
    titleI18nKey: "section_users_title",
    fallbackTitle: "Users",
    subtitleI18nKey: "section_users_subtitle",
    fallbackSubtitle: "Search, bans, and account actions",
    icon: UsersRound,
    loadComponent: () => import("./UsersSection.svelte").then((module) => module.default),
  },
  {
    id: "payments",
    group: "operations",
    order: 20,
    i18nKey: "nav_payments",
    fallbackLabel: "Payments",
    titleI18nKey: "section_payments_title",
    fallbackTitle: "Payments",
    subtitleI18nKey: "section_payments_subtitle",
    fallbackSubtitle: "Transaction history and export",
    icon: CreditCard,
    loadComponent: () => import("./PaymentsSection.svelte").then((module) => module.default),
  },
  {
    id: "promos",
    group: "operations",
    order: 30,
    i18nKey: "nav_promos",
    fallbackLabel: "Promos",
    titleI18nKey: "section_promos_title",
    fallbackTitle: "Promos",
    subtitleI18nKey: "section_promos_subtitle",
    fallbackSubtitle: "Create and manage promo codes",
    icon: Tag,
    loadComponent: () => import("./PromosSection.svelte").then((module) => module.default),
  },
  {
    id: "ads",
    group: "operations",
    order: 40,
    i18nKey: "nav_ads",
    fallbackLabel: "Ads",
    titleI18nKey: "section_ads_title",
    fallbackTitle: "Ad Campaigns",
    subtitleI18nKey: "section_ads_subtitle",
    fallbackSubtitle: "UTM sources and attribution",
    icon: Sparkles,
    loadComponent: () => import("./AdsSection.svelte").then((module) => module.default),
  },
  {
    id: "broadcast",
    group: "communication",
    order: 10,
    i18nKey: "nav_broadcast",
    fallbackLabel: "Broadcast",
    titleI18nKey: "section_broadcast_title",
    fallbackTitle: "Broadcast",
    subtitleI18nKey: "section_broadcast_subtitle",
    fallbackSubtitle: "Mass messaging in Telegram",
    icon: Megaphone,
    loadComponent: () => import("./BroadcastSection.svelte").then((module) => module.default),
  },
  {
    id: "logs",
    group: "communication",
    order: 20,
    i18nKey: "nav_logs",
    fallbackLabel: "Logs",
    titleI18nKey: "section_logs_title",
    fallbackTitle: "Activity Logs",
    subtitleI18nKey: "section_logs_subtitle",
    fallbackSubtitle: "User events and admin actions",
    icon: FileText,
    loadComponent: () => import("./LogsSection.svelte").then((module) => module.default),
  },
  {
    id: "support",
    group: "communication",
    order: 30,
    i18nKey: "nav_support",
    fallbackLabel: "Support",
    titleI18nKey: "section_support_title",
    fallbackTitle: "Support",
    subtitleI18nKey: "section_support_subtitle",
    fallbackSubtitle: "Ticket inbox and user replies",
    icon: LifeBuoy,
    loadComponent: () => import("./SupportSection.svelte").then((module) => module.default),
  },
  {
    id: "tariffs",
    group: "system",
    order: 10,
    i18nKey: "nav_tariffs",
    fallbackLabel: "Tariffs",
    titleI18nKey: "section_tariffs_title",
    fallbackTitle: "Tariffs",
    subtitleI18nKey: "section_tariffs_subtitle",
    fallbackSubtitle: "Sales catalog, periods, packages, and limits",
    icon: Coins,
    loadComponent: () => import("./TariffsSection.svelte").then((module) => module.default),
  },
  {
    id: "appearance",
    group: "system",
    order: 20,
    i18nKey: "nav_appearance",
    fallbackLabel: "Appearance",
    titleI18nKey: "section_appearance_title",
    fallbackTitle: "Appearance",
    subtitleI18nKey: "section_appearance_subtitle",
    fallbackSubtitle: "Logo, themes, and Mini App accent colors",
    icon: Paintbrush,
    loadComponent: () => import("./AppearanceSection.svelte").then((module) => module.default),
  },
  {
    id: "translations",
    group: "system",
    order: 30,
    i18nKey: "nav_translations",
    fallbackLabel: "Translations",
    titleI18nKey: "section_translations_title",
    fallbackTitle: "Translations",
    subtitleI18nKey: "section_translations_subtitle",
    fallbackSubtitle:
      "Runtime localization string overrides from DB and data/locales-overrides.json",
    icon: Languages,
    loadComponent: () => import("./TranslationsSection.svelte").then((module) => module.default),
  },
  {
    id: "backups",
    group: "system",
    order: 40,
    i18nKey: "nav_backups",
    fallbackLabel: "Backups",
    titleI18nKey: "section_backups_title",
    fallbackTitle: "Backups",
    subtitleI18nKey: "section_backups_subtitle",
    fallbackSubtitle: "Archives, uploads, and database/compose restore",
    icon: Database,
    loadComponent: () => import("./BackupsSection.svelte").then((module) => module.default),
  },
  {
    id: "settings",
    group: "system",
    order: 50,
    i18nKey: "nav_settings",
    fallbackLabel: "Settings",
    titleI18nKey: "section_settings_title",
    fallbackTitle: "App Settings",
    subtitleI18nKey: "section_settings_subtitle",
    fallbackSubtitle: "Overrides for .env, applied instantly",
    icon: Sliders,
    loadComponent: () => import("./SettingsSection.svelte").then((module) => module.default),
  },
];

function extensionSections(): AdminSectionDescriptor[] {
  const modules = import.meta.glob("./extensions/*.ts", {
    eager: true,
    import: "default",
  }) as Record<string, AdminSectionDescriptor | AdminSectionDescriptor[]>;
  // Build-time extensions are sorted by path first and then by descriptor order
  // below. This keeps output deterministic while letting extended builds add
  // files without editing the core registry.
  return Object.keys(modules)
    .sort()
    .flatMap((key) => modules[key] || []);
}

export const ADMIN_SECTIONS = [...CORE_ADMIN_SECTIONS, ...extensionSections()]
  .filter((section) => section?.id && (section?.component || section?.loadComponent))
  .sort((a, b) => a.group.localeCompare(b.group) || a.order - b.order || a.id.localeCompare(b.id));
