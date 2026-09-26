/** Runtime descriptors from verified packages. The host owns their metadata. */

import { Key, Sparkles, TrendingUp, Zap } from "$components/ui/icons.js";
import {
  ADMIN_SECTION_TABS,
  ADMIN_USER_DETAIL_PANELS,
  ADMIN_UI_SLOTS,
  adminExtensionRevision,
} from "./extensionRegistry";
import {
  ADMIN_SECTION_GROUPS,
  addRuntimeAdminSections,
  removeRuntimeAdminSections,
  ADMIN_SECTIONS,
} from "./registry";
import type {
  AdminSectionDescriptor,
  AdminSectionGroupDescriptor,
  AdminSectionTabDescriptor,
  AdminUserDetailPanelDescriptor,
  AdminUiSlotDescriptor,
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
  titleI18nKey?: string;
  title?: string;
  subtitleI18nKey?: string;
  subtitle?: string;
  requiredFeature?: string;
  visibleWhenLocked?: boolean;
  hideInNavigation?: boolean;
  routeAliases?: string[];
  routeDefaults?: AdminSectionDescriptor["routeDefaults"];
  icon?: string;
  target?: string;
  placement?: "before" | "after" | "replace";
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
  slots?: RuntimeView[];
};

let runtimeSections: AdminSectionDescriptor[] = [];
let runtimeGroups: AdminSectionGroupDescriptor[] = [];
let runtimeTabs: AdminSectionTabDescriptor[] = [];
let runtimePanels: AdminUserDetailPanelDescriptor[] = [];
let runtimeSlots: AdminUiSlotDescriptor[] = [];
let runtimeStyles: HTMLLinkElement[] = [];

function removeOwned<T>(registry: T[], previous: T[]) {
  const owned = new Set(previous);
  for (let i = registry.length - 1; i >= 0; i--) if (owned.has(registry[i])) registry.splice(i, 1);
}

const RUNTIME_ICONS: Record<string, unknown> = {
  key: Key,
  zap: Zap,
  "trending-up": TrendingUp,
};

function validView(plugin: RuntimePlugin, view: RuntimeView): boolean {
  return Boolean(
    /^[a-z][a-z0-9-]{1,63}$/.test(plugin.id) &&
    /^[a-f0-9]{64}$/.test(plugin.digest) &&
    /^[a-z][a-z0-9-]+$/.test(view.id) &&
    /^[a-z][a-z0-9-]+$/.test(view.view) &&
    plugin.entry.startsWith(`/api/admin/plugins/assets/${plugin.id}/${plugin.digest}/`)
  );
}

function common(plugin: RuntimePlugin, view: RuntimeView, namespaced = false) {
  return {
    id: namespaced ? `${plugin.id}:${view.id}` : view.id,
    order: view.order ?? 100,
    i18nKey: view.i18nKey || view.id.replaceAll("-", "_"),
    fallbackLabel: view.label || view.id,
    requiredFeature: view.requiredFeature,
    visibleWhenLocked: view.visibleWhenLocked,
    runtimeViewId: view.view,
    runtimeEntry: plugin.entry,
    runtimeDigest: plugin.digest,
  };
}

export function registerRuntimeExtensions(plugins: readonly RuntimePlugin[]): void {
  removeRuntimeAdminSections(runtimeSections);
  removeOwned(ADMIN_SECTION_GROUPS, runtimeGroups);
  removeOwned(ADMIN_SECTION_TABS, runtimeTabs);
  removeOwned(ADMIN_USER_DETAIL_PANELS, runtimePanels);
  removeOwned(ADMIN_UI_SLOTS, runtimeSlots);
  runtimeStyles.forEach((style) => style.remove());
  runtimeGroups = [];
  runtimeTabs = [];
  runtimePanels = [];
  runtimeSlots = [];
  runtimeStyles = [];
  const sections: AdminSectionDescriptor[] = [];
  for (const plugin of plugins) {
    if (
      !/^[a-z][a-z0-9-]{1,63}$/.test(plugin.id) ||
      !/^[a-f0-9]{64}$/.test(plugin.digest) ||
      !plugin.entry.startsWith(`/api/admin/plugins/assets/${plugin.id}/${plugin.digest}/`)
    )
      continue;
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
      runtimeGroups.push(descriptor);
    }
    for (const view of plugin.sections || []) {
      if (!validView(plugin, view)) continue;
      sections.push({
        ...common(plugin, view),
        group: view.group || "system",
        titleI18nKey:
          view.titleI18nKey || (view.i18nKey ? `${view.i18nKey}_title` : `${view.id}_title`),
        fallbackTitle: view.title || view.label || view.id,
        subtitleI18nKey:
          view.subtitleI18nKey ||
          (view.i18nKey ? `${view.i18nKey}_subtitle` : `${view.id}_subtitle`),
        fallbackSubtitle: view.subtitle || "",
        icon: RUNTIME_ICONS[view.icon || ""] || Sparkles,
        component: PluginHost,
        hideInNavigation: view.hideInNavigation === true,
        routeAliases: view.routeAliases,
        routeDefaults: view.routeDefaults,
      });
    }
    for (const view of plugin.section_tabs || []) {
      if (!validView(plugin, view) || !view.sectionId) continue;
      const descriptor: AdminSectionTabDescriptor = {
        ...common(plugin, view, true),
        sectionId: view.sectionId,
        component: PluginHost,
      };
      if (
        !ADMIN_SECTION_TABS.some(
          (existing) => existing.sectionId === descriptor.sectionId && existing.id === descriptor.id
        )
      ) {
        ADMIN_SECTION_TABS.push(descriptor);
        runtimeTabs.push(descriptor);
      }
    }
    for (const view of plugin.user_panels || []) {
      if (!validView(plugin, view)) continue;
      const descriptor: AdminUserDetailPanelDescriptor = {
        ...common(plugin, view, true),
        component: PluginHost,
      };
      if (!ADMIN_USER_DETAIL_PANELS.some((existing) => existing.id === descriptor.id)) {
        ADMIN_USER_DETAIL_PANELS.push(descriptor);
        runtimePanels.push(descriptor);
      }
    }
    for (const view of plugin.slots || []) {
      if (!validView(plugin, view) || !view.target) continue;
      const descriptor: AdminUiSlotDescriptor = {
        ...common(plugin, view, true),
        sectionId: view.target.split(".")[1],
        target: view.target,
        placement: view.placement || "after",
        component: PluginHost,
      };
      if (!ADMIN_UI_SLOTS.some((existing) => existing.id === descriptor.id)) {
        ADMIN_UI_SLOTS.push(descriptor);
        runtimeSlots.push(descriptor);
      }
    }
    for (const style of plugin.styles || []) {
      if (!style.startsWith(`/api/admin/plugins/assets/${plugin.id}/${plugin.digest}/`)) continue;
      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = style;
      document.head.appendChild(link);
      runtimeStyles.push(link);
    }
  }
  runtimeSections = sections.filter(
    (section) => !ADMIN_SECTIONS.some((existing) => existing.id === section.id)
  );
  addRuntimeAdminSections(runtimeSections);
  ADMIN_SECTION_GROUPS.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  ADMIN_SECTION_TABS.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  ADMIN_USER_DETAIL_PANELS.sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
  adminExtensionRevision.update((value) => value + 1);
}
