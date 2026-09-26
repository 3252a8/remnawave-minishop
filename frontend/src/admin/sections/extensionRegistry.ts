import type {
  AdminSectionDescriptor,
  AdminSectionGroupDescriptor,
  AdminSectionTabDescriptor,
  AdminUserDetailPanelDescriptor,
  AdminUiSlotDescriptor,
} from "./extensionTypes";
import { writable } from "svelte/store";

type AdminExtensionModule = {
  default?: AdminSectionDescriptor | AdminSectionDescriptor[];
  sectionGroups?: AdminSectionGroupDescriptor | AdminSectionGroupDescriptor[];
  sectionTabs?: AdminSectionTabDescriptor | AdminSectionTabDescriptor[];
  userDetailPanels?: AdminUserDetailPanelDescriptor | AdminUserDetailPanelDescriptor[];
  uiSlots?: AdminUiSlotDescriptor | AdminUiSlotDescriptor[];
};

const extensionModules = import.meta.glob("./extensions/*.ts", {
  eager: true,
}) as Record<string, AdminExtensionModule>;

function extensionModuleValues(): AdminExtensionModule[] {
  return Object.keys(extensionModules)
    .sort()
    .map((path) => extensionModules[path]);
}

function arrayOf<T>(value: T | T[] | null | undefined): T[] {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

export const ADMIN_SECTION_EXTENSIONS = extensionModuleValues().flatMap((module) =>
  arrayOf(module.default)
);

export const ADMIN_SECTION_GROUP_EXTENSIONS = extensionModuleValues()
  .flatMap((module) => arrayOf(module.sectionGroups))
  .filter((group) => group?.id && group?.i18nKey)
  .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));

export const ADMIN_SECTION_TABS = extensionModuleValues()
  .flatMap((module) => arrayOf(module.sectionTabs))
  .filter((tab) => tab?.id && tab?.sectionId && tab?.component)
  .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));

export const ADMIN_USER_DETAIL_PANELS = extensionModuleValues()
  .flatMap((module) => arrayOf(module.userDetailPanels))
  .filter((panel) => panel?.id && panel?.component)
  .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));

export const ADMIN_UI_SLOTS = extensionModuleValues().flatMap((module) => arrayOf(module.uiSlots));
export const adminExtensionRevision = writable(0);
