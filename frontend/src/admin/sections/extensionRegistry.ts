import type { AdminSectionDescriptor, AdminUserDetailPanelDescriptor } from "./extensionTypes";

type AdminExtensionModule = {
  default?: AdminSectionDescriptor | AdminSectionDescriptor[];
  userDetailPanels?: AdminUserDetailPanelDescriptor | AdminUserDetailPanelDescriptor[];
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

export const ADMIN_USER_DETAIL_PANELS = extensionModuleValues()
  .flatMap((module) => arrayOf(module.userDetailPanels))
  .filter((panel) => panel?.id && panel?.component)
  .sort((left, right) => left.order - right.order || left.id.localeCompare(right.id));
