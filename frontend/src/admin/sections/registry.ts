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

import AdsSection from "./AdsSection.svelte";
import AppearanceSection from "./AppearanceSection.svelte";
import BackupsSection from "./BackupsSection.svelte";
import BroadcastSection from "./BroadcastSection.svelte";
import LogsSection from "./LogsSection.svelte";
import PaymentsSection from "./PaymentsSection.svelte";
import PromosSection from "./PromosSection.svelte";
import SettingsSection from "./SettingsSection.svelte";
import StatsSection from "./StatsSection.svelte";
import SupportSection from "./SupportSection.svelte";
import TariffsSection from "./TariffsSection.svelte";
import TranslationsSection from "./TranslationsSection.svelte";
import UsersSection from "./UsersSection.svelte";

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
  component: unknown;
  feature?: string;
}

export const ADMIN_SECTION_GROUPS = [
  { id: "overview", order: 10, i18nKey: "nav_overview", fallbackLabel: "Обзор" },
  { id: "operations", order: 20, i18nKey: "nav_operations", fallbackLabel: "Управление" },
  {
    id: "communication",
    order: 30,
    i18nKey: "nav_communication",
    fallbackLabel: "Коммуникации",
  },
  { id: "system", order: 40, i18nKey: "nav_system", fallbackLabel: "Система" },
];

const CORE_ADMIN_SECTIONS: AdminSectionDescriptor[] = [
  {
    id: "stats",
    group: "overview",
    order: 10,
    i18nKey: "nav_dashboard",
    fallbackLabel: "Дашборд",
    titleI18nKey: "section_stats_title",
    fallbackTitle: "Дашборд",
    subtitleI18nKey: "section_stats_subtitle",
    fallbackSubtitle: "Аудитория, доходы, панель Remnawave и последние платежи",
    icon: LayoutDashboard,
    component: StatsSection,
  },
  {
    id: "users",
    group: "operations",
    order: 10,
    i18nKey: "nav_users",
    fallbackLabel: "Пользователи",
    titleI18nKey: "section_users_title",
    fallbackTitle: "Пользователи",
    subtitleI18nKey: "section_users_subtitle",
    fallbackSubtitle: "Поиск, баны и действия над аккаунтами",
    icon: UsersRound,
    component: UsersSection,
  },
  {
    id: "payments",
    group: "operations",
    order: 20,
    i18nKey: "nav_payments",
    fallbackLabel: "Платежи",
    titleI18nKey: "section_payments_title",
    fallbackTitle: "Платежи",
    subtitleI18nKey: "section_payments_subtitle",
    fallbackSubtitle: "История транзакций и экспорт",
    icon: CreditCard,
    component: PaymentsSection,
  },
  {
    id: "promos",
    group: "operations",
    order: 30,
    i18nKey: "nav_promos",
    fallbackLabel: "Промокоды",
    titleI18nKey: "section_promos_title",
    fallbackTitle: "Промокоды",
    subtitleI18nKey: "section_promos_subtitle",
    fallbackSubtitle: "Создание и управление кодами",
    icon: Tag,
    component: PromosSection,
  },
  {
    id: "ads",
    group: "operations",
    order: 40,
    i18nKey: "nav_ads",
    fallbackLabel: "Реклама",
    titleI18nKey: "section_ads_title",
    fallbackTitle: "Рекламные кампании",
    subtitleI18nKey: "section_ads_subtitle",
    fallbackSubtitle: "UTM-источники и атрибуция",
    icon: Sparkles,
    component: AdsSection,
  },
  {
    id: "broadcast",
    group: "communication",
    order: 10,
    i18nKey: "nav_broadcast",
    fallbackLabel: "Рассылка",
    titleI18nKey: "section_broadcast_title",
    fallbackTitle: "Рассылка",
    subtitleI18nKey: "section_broadcast_subtitle",
    fallbackSubtitle: "Массовая отправка сообщений в Telegram",
    icon: Megaphone,
    component: BroadcastSection,
  },
  {
    id: "logs",
    group: "communication",
    order: 20,
    i18nKey: "nav_logs",
    fallbackLabel: "Логи",
    titleI18nKey: "section_logs_title",
    fallbackTitle: "Логи активности",
    subtitleI18nKey: "section_logs_subtitle",
    fallbackSubtitle: "События пользователей и админ-действия",
    icon: FileText,
    component: LogsSection,
  },
  {
    id: "support",
    group: "communication",
    order: 30,
    i18nKey: "nav_support",
    fallbackLabel: "Поддержка",
    titleI18nKey: "section_support_title",
    fallbackTitle: "Поддержка",
    subtitleI18nKey: "section_support_subtitle",
    fallbackSubtitle: "Инбокс тикетов и ответы пользователям",
    icon: LifeBuoy,
    component: SupportSection,
  },
  {
    id: "tariffs",
    group: "system",
    order: 10,
    i18nKey: "nav_tariffs",
    fallbackLabel: "Тарифы",
    titleI18nKey: "section_tariffs_title",
    fallbackTitle: "Тарифы",
    subtitleI18nKey: "section_tariffs_subtitle",
    fallbackSubtitle: "Каталог продаж, периоды, пакеты и лимиты",
    icon: Coins,
    component: TariffsSection,
  },
  {
    id: "appearance",
    group: "system",
    order: 20,
    i18nKey: "nav_appearance",
    fallbackLabel: "Внешний вид",
    titleI18nKey: "section_appearance_title",
    fallbackTitle: "Внешний вид",
    subtitleI18nKey: "section_appearance_subtitle",
    fallbackSubtitle: "Логотип, темы и акцентные цвета Mini App",
    icon: Paintbrush,
    component: AppearanceSection,
  },
  {
    id: "translations",
    group: "system",
    order: 30,
    i18nKey: "nav_translations",
    fallbackLabel: "Переводы",
    titleI18nKey: "section_translations_title",
    fallbackTitle: "Переводы",
    subtitleI18nKey: "section_translations_subtitle",
    fallbackSubtitle: "Оверрайды строк локализации из базы данных и data/locales-overrides.json",
    icon: Languages,
    component: TranslationsSection,
  },
  {
    id: "backups",
    group: "system",
    order: 40,
    i18nKey: "nav_backups",
    fallbackLabel: "Бэкапы",
    titleI18nKey: "section_backups_title",
    fallbackTitle: "Бэкапы",
    subtitleI18nKey: "section_backups_subtitle",
    fallbackSubtitle: "Архивы, загрузка и восстановление БД/compose",
    icon: Database,
    component: BackupsSection,
  },
  {
    id: "settings",
    group: "system",
    order: 50,
    i18nKey: "nav_settings",
    fallbackLabel: "Настройки",
    titleI18nKey: "section_settings_title",
    fallbackTitle: "Настройки приложения",
    subtitleI18nKey: "section_settings_subtitle",
    fallbackSubtitle: "Оверрайды над .env, применяются мгновенно",
    icon: Sliders,
    component: SettingsSection,
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
  .filter((section) => section?.id && section?.component)
  .sort((a, b) => a.group.localeCompare(b.group) || a.order - b.order || a.id.localeCompare(b.id));
