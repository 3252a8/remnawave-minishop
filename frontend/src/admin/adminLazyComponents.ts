import type { ComponentType, SvelteComponent } from "svelte";

import type { AdminSectionDescriptor } from "./sections/registry";

export type DynamicComponent = ComponentType<SvelteComponent<Record<string, unknown>>>;

export function dynamicComponent(component: unknown): DynamicComponent {
  return component as DynamicComponent;
}

export function componentFromModule(value: unknown): DynamicComponent | null {
  if (!value) return null;
  if (typeof value === "object" && "default" in value) {
    return dynamicComponent((value as { default?: unknown }).default);
  }
  return dynamicComponent(value);
}

export function createAdminSectionComponentLoader() {
  const loadedSectionComponents = new Map<string, DynamicComponent>();

  async function load(section: AdminSectionDescriptor): Promise<DynamicComponent> {
    const cached = loadedSectionComponents.get(section.id);
    if (cached) return cached;
    const component = section.component
      ? dynamicComponent(section.component)
      : componentFromModule(await section.loadComponent?.());
    if (!component) throw new Error(`admin_section_component_missing:${section.id}`);
    loadedSectionComponents.set(section.id, component);
    return component;
  }

  function warm(section: AdminSectionDescriptor): void {
    if (loadedSectionComponents.has(section.id) || section.component) return;
    void load(section).catch(() => {});
  }

  return { load, warm };
}

export function loadDynamicComponent(
  current: DynamicComponent | null,
  importer: () => Promise<{ default: unknown }>,
  assign: (component: DynamicComponent) => void
): void {
  if (current) return;
  void importer().then((module) => {
    assign(dynamicComponent(module.default));
  });
}
