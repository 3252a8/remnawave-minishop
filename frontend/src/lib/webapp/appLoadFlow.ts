import { activeTabForWebappSection, resolveAvailableWebappSection } from "./sectionAvailability.js";
import {
  normalizeAdminSection,
  normalizeSection,
  sectionFromPath,
  supportTicketIdFromPath,
  withRoutePrefix,
} from "./routes.js";

type WebappRecord = Record<string, unknown>;

export type InitialLoadRouteInput = {
  activeTab: string;
  adminActiveSection: string;
  fallbackAdminSection: string;
  mock: boolean;
  pathname: string;
  preserveView?: boolean;
  routePrefix?: string;
  screen: string;
  screenQuery?: string | null;
  section?: string | null;
  adminSection?: string | null;
};

export type InitialLoadRoute = {
  preservedAdminSection: string | null;
  preservedSection: string | null;
  routeSection: string;
  shouldPreloadInstallGuides: boolean;
};

export type LoadedWebappRouteInput = {
  fallbackAdminSection: string;
  payload: WebappRecord;
  preservedAdminSection?: string | null;
  routeSection: string;
};

export type LoadedWebappRoute = {
  activeTab: string;
  initialAdminSection: string | null;
  isAdmin: boolean;
  section: string;
  shouldPrefetchAdminAssets: boolean;
  supportEnabled: boolean;
};

export type SupportLoadRoute = {
  initialSupportTicketId: number | null;
  targetPath: string | null;
};

function recordField(value: unknown): WebappRecord {
  return value && typeof value === "object" ? (value as WebappRecord) : {};
}

export function resolveInitialLoadRoute({
  activeTab,
  adminActiveSection,
  fallbackAdminSection,
  mock,
  pathname,
  preserveView = false,
  routePrefix = "",
  screen,
  screenQuery = null,
  section,
  adminSection,
}: InitialLoadRouteInput): InitialLoadRoute {
  const preservedSection = preserveView ? normalizeSection(section || screen || activeTab) : null;
  const preservedAdminSection =
    preserveView && preservedSection === "admin"
      ? normalizeAdminSection(adminSection || adminActiveSection || fallbackAdminSection)
      : null;
  const routeSection = preserveView
    ? preservedSection || "home"
    : mock && screenQuery
      ? normalizeSection(screenQuery)
      : sectionFromPath(pathname, routePrefix);

  return {
    preservedAdminSection,
    preservedSection,
    routeSection,
    shouldPreloadInstallGuides: routeSection === "install",
  };
}

export function resolveLoadedWebappRoute({
  fallbackAdminSection,
  payload,
  preservedAdminSection = null,
  routeSection,
}: LoadedWebappRouteInput): LoadedWebappRoute {
  const settings = recordField(payload.settings);
  const subscription = recordField(payload.subscription);
  const user = recordField(payload.user);
  const isAdmin = Boolean(user.is_admin);
  const section = resolveAvailableWebappSection({
    devicesEnabled: Boolean(settings.my_devices_enabled),
    installGuidesAvailable: Boolean(settings.subscription_guides_enabled && subscription.active),
    isAdmin,
    section: String(routeSection || "home"),
    supportEnabled: settings.support_tickets_enabled !== false,
  });
  return {
    activeTab: activeTabForWebappSection(section),
    initialAdminSection:
      section === "admin"
        ? preservedAdminSection || normalizeAdminSection(fallbackAdminSection)
        : null,
    isAdmin,
    section,
    shouldPrefetchAdminAssets: isAdmin && section !== "admin",
    supportEnabled: settings.support_tickets_enabled !== false,
  };
}

export function resolveSupportLoadRoute({
  pathname,
  routePrefix = "",
  section,
}: {
  pathname: string;
  routePrefix?: string;
  section: string;
}): SupportLoadRoute {
  const initialSupportTicketId =
    section === "support" ? supportTicketIdFromPath(pathname, routePrefix) : null;
  return {
    initialSupportTicketId,
    targetPath: initialSupportTicketId
      ? withRoutePrefix(`/support/${initialSupportTicketId}`, routePrefix)
      : null,
  };
}
