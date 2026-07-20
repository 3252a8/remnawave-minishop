import type { Component } from "svelte";

import type { AdminUser } from "$lib/admin/stores/usersStore";
import type { AdminUserDetail } from "$lib/admin/stores/usersStoreState";
import type { TranslateFn } from "./user-detail/userDetailTypes";

interface FeatureBoundDescriptor {
  /** @deprecated Prefer requiredFeature for new extension descriptors. */
  feature?: string;
  requiredFeature?: string;
  visibleWhenLocked?: boolean;
}

export interface AdminSectionGroupDescriptor {
  id: string;
  order: number;
  i18nKey: string;
  fallbackLabel: string;
}

export interface AdminSectionComponentProps {
  at: TranslateFn;
  featureAvailable: boolean;
  availableFeatures: readonly string[];
  routePrefix: string;
  onNavigateSection: (sectionId: string) => void;
}

export interface AdminSectionDescriptor extends FeatureBoundDescriptor {
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
}

export interface AdminUserDetailPanelProps {
  at: TranslateFn;
  user: AdminUser;
  userDetail: AdminUserDetail;
  featureAvailable: boolean;
  active: boolean;
  routePrefix: string;
}

export interface AdminUserDetailPanelDescriptor extends FeatureBoundDescriptor {
  id: string;
  order: number;
  i18nKey: string;
  fallbackLabel: string;
  component: Component<AdminUserDetailPanelProps>;
}

export function requiredFeatureForDescriptor(descriptor: FeatureBoundDescriptor): string {
  return String(descriptor.requiredFeature || descriptor.feature || "").trim();
}

export function isFeatureBoundDescriptorVisible(
  descriptor: FeatureBoundDescriptor,
  availableFeatures: ReadonlySet<string>
): boolean {
  const requiredFeature = requiredFeatureForDescriptor(descriptor);
  return (
    !requiredFeature ||
    availableFeatures.has(requiredFeature) ||
    Boolean(descriptor.visibleWhenLocked)
  );
}
