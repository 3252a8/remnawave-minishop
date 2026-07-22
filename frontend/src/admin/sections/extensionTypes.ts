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
  /**
   * True once the runtime feature manifest has been loaded at least once.
   * Until then a missing feature means "still discovering", not "locked", so
   * feature-bound sections can render a pending state instead of a lock.
   */
  featuresResolved: boolean;
  availableFeatures: readonly string[];
  routePrefix: string;
  onNavigateSection: (sectionId: string) => void;
  /**
   * Opens the core user card for the given user id. The panel wires the
   * section-appropriate handler at runtime; extensions may rely on it being
   * present for admin sections.
   */
  onOpenUserCard: (userId: number) => void;
}

export interface AdminSectionRouteDefault {
  /**
   * The default applies only when this feature is available. Extension
   * descriptors use this neutral routing rule without teaching core about
   * their feature names or query semantics.
   */
  requiredFeature?: string;
  query: Readonly<Record<string, string>>;
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
  /**
   * Legacy route slugs that canonicalize to this section id. Aliases keep old
   * bookmarks working when an extension renames or merges its sections; they
   * never override another registered section id.
   */
  routeAliases?: readonly string[];
  /**
   * Ordered query defaults for sidebar navigation. Existing direct URLs are
   * not rewritten by core; extensions may canonicalize their own aliases.
   */
  routeDefaults?: readonly AdminSectionRouteDefault[];
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
