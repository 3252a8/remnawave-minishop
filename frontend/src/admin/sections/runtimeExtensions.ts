/** Runtime descriptors from verified packages. The host owns their metadata. */

import { Key, Sparkles, TrendingUp, Zap } from "$components/ui/icons.js";
import { ADMIN_SECTION_TABS, ADMIN_USER_DETAIL_PANELS } from "./extensionRegistry";
import { ADMIN_SECTION_GROUPS, addRuntimeAdminSections } from "./registry";
import type {
  AdminSectionDescriptor,
  AdminSectionGroupDescriptor,
  AdminSectionTabDescriptor,
  AdminUserDetailPanelDescriptor,
} from "./extensionTypes";
import PluginHost from "./PluginHost.svelte";

type RuntimeView = {
  id: string;
  view: string;
  order?: number;
  group?: string;
  sectionId?: string;
  i18nKey?: string;
  label?: string;
  title?: string;
  subtitle?: string;
  requiredFeature?: string;
  visibleWhenLocked?: boolean;
  routeAliases?: string[];
  routeDefaults?: AdminSectionDescriptor["routeDefaults"];
  icon?: string;
};

type RuntimePlugin = {
  id: string;
  digest: string;
  entry: string;
  styles?: string[];
  sections?: RuntimeView[];
  section_groups?: Array<{ id: string; order: number; label: string }>;
  section_tabs?: RuntimeView[];
  user_panels?: RuntimeView[];
};

const RUNTIME_ICONS: Record<string, unknown> = {
  key: Key,
  zap: Zap,
  "trending-up": TrendingUp,
};

function validView(plugin: RuntimePlugin, view: RuntimeView): boolean {
  return Boolean(
    /^[a-z][a-z0-9-]+$/.test(plugin.id) &&
    /^[a-z][a-z0-9-]+$/.test(view.id) &&
    /^[a-z][a-z0-9-]+$/.test(view.view) &&
    plugin.entry.startsWith(`/api/admin/plugins/assets/${plugin.id}/${plugin.digest}/`)
  );
}

function common(plugin: RuntimePlugin, view: RuntimeView) {
  return {
    id: view.id,
    order: Number(view.order || 100),
    i18nKey: view.i18nKey || view.id.replaceAll("-", "_"),
    fallbackLabel: view.label || view.id,
    requiredFeature: view.requiredFeature,
    visibleWhenLocked: view.visibleWhenLocked,
    runtimeViewId: view.view,
    runtimeEntry: plugin.entry,
  };
}

export function registerRuntimeExtensions(plugins: readonly RuntimePlugin[]): void {
  const sections: AdminSectionDescriptor[] = [];
  for (const plugin of plugins) {
    if (!Array.isArray(plugin.sections)) continue;
    for (const group of plugin.section_groups || []) {
      if (!group.id.startsWith(`${plugin.id}-`)) continue;
      if (ADMIN_SECTION_GROUPS.some((existing) => existing.id === group.id)) continue;
      const descriptor: AdminSectionGroupDescriptor = {
        id: group.id,
        order: group.order,
        i18nKey: group.id.replaceAll("-", "_"),
        fallbackLabel: group.label,
      };
      ADMIN_SECTION_GROUPS.push(descriptor);
    }
    for (const view of plugin.sections) {
      if (!validView(plugin, view)) continue;
      sections.push({
        ...common(plugin, view),
        group: view.group || "system",
        titleI18nKey: view.i18nKey ? `${view.i18nKey}_title` : `${view.id}_title`,
        fallbackTitle: view.title || view.label || view.id,
        subtitleI18nKey: view.i18nKey ? `${view.i18nKey}_subtitle` : `${view.id}_subtitle`,
        fallbackSubtitle: view.subtitle || "",
        icon: RUNTIME_ICONS[view.icon || ""] || Sparkles,
        component: PluginHost,
        routeAliases: view.routeAliases,
        routeDefaults: view.routeDefaults,
      });
    }
    for (const view of plugin.section_tabs || []) {
      if (!validView(plugin, view) || !view.sectionId) continue;
      const descriptor: AdminSectionTabDescriptor = {
        ...common(plugin, view),
        sectionId: view.sectionId,
        component: PluginHost,
      };
      if (!ADMIN_SECTION_TABS.some((existing) => existing.id === descriptor.id))
        ADMIN_SECTION_TABS.push(descriptor);
    }
    for (const view of plugin.user_panels || []) {
      if (!validView(plugin, view)) continue;
      const descriptor: AdminUserDetailPanelDescriptor = {
        ...common(plugin, view),
        component: PluginHost,
      };
      if (!ADMIN_USER_DETAIL_PANELS.some((existing) => existing.id === descriptor.id))
        ADMIN_USER_DETAIL_PANELS.push(descriptor);
    }
    for (const style of plugin.styles || []) {
      if (!style.startsWith(`/api/admin/plugins/assets/${plugin.id}/${plugin.digest}/`)) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = style;
      document.head.appendChild(link);
    }
  }
  addRuntimeAdminSections(sections);
  ADMIN_SECTION_GROUPS.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  ADMIN_SECTION_TABS.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  ADMIN_USER_DETAIL_PANELS.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
}
