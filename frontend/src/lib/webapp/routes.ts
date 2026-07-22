import { ADMIN_SECTIONS, APP_SECTION_PATHS } from "./constants";

export type WebappSection =
  "home" | "invite" | "install" | "trial" | "devices" | "support" | "settings" | "admin";

type AdminUserRouteId = string | number | boolean | null | undefined;

export function normalizeSection(value: unknown): WebappSection {
  const section = String(value || "")
    .trim()
    .toLowerCase();
  if (
    section === "invite" ||
    section === "install" ||
    section === "trial" ||
    section === "devices" ||
    section === "support" ||
    section === "settings" ||
    section === "admin"
  ) {
    return section;
  }
  return "home";
}

const ADMIN_SECTION_SLUG_RE = /^[a-z0-9][a-z0-9_-]*$/;

export function normalizeAdminSection(value: unknown): string {
  const section = String(value || "")
    .trim()
    .toLowerCase();
  if (ADMIN_SECTIONS.has(section)) return section;
  // Extension sections register in the admin bundle's registry, which is not
  // loaded at boot. Keep any well-formed slug so extension deep links survive
  // until the admin panel validates them against the full section registry;
  // only malformed slugs fall back to the dashboard here.
  return ADMIN_SECTION_SLUG_RE.test(section) ? section : "stats";
}

function normalizePathname(pathname: unknown): string {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  return normalized || "/";
}

export function stripRoutePrefix(pathname: unknown, routePrefix: unknown = ""): string {
  const path = normalizePathname(pathname);
  const prefix = normalizePathname(routePrefix);
  if (prefix === "/") return path;
  if (path.toLowerCase() === prefix.toLowerCase()) return "/";
  if (path.toLowerCase().startsWith(`${prefix.toLowerCase()}/`)) {
    return path.slice(prefix.length) || "/";
  }
  return path;
}

export function withRoutePrefix(pathname: unknown, routePrefix: unknown = ""): string {
  const path = normalizePathname(pathname);
  const prefix = normalizePathname(routePrefix);
  if (prefix === "/") return path;
  if (path === "/") return prefix;
  return `${prefix}${path}`;
}

export function sectionFromPath(pathname: unknown, routePrefix: unknown = ""): WebappSection {
  const normalizedPath = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  const routePath = stripRoutePrefix(normalizedPath, routePrefix).toLowerCase().replace(/\/+$/, "");
  if (!routePath || routePath === "/") return "home";
  if (routePath === "/admin" || routePath.startsWith("/admin/")) return "admin";
  if (routePath === "/support" || routePath.startsWith("/support/")) return "support";
  const section = routePath.startsWith("/") ? routePath.slice(1) : routePath;
  return normalizeSection(section);
}

export function publicInstallTokenFromPath(pathname: unknown): string {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  const match = normalized.match(/^\/s\/([a-f0-9]{32})$/i);
  return match ? match[1].toLowerCase() : "";
}

export function adminSectionFromPath(pathname: unknown, routePrefix: unknown = ""): string {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/([a-z0-9_-]+)(?:\/.*)?$/);
  return normalizeAdminSection(m ? m[1] : "");
}

function decodePathSegment(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

export function adminSettingsPathFromPath(pathname: unknown, routePrefix: unknown = ""): string[] {
  const normalized = stripRoutePrefix(pathname, routePrefix).replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/settings(?:\/(.*))?$/i);
  if (!m?.[1]) return [];
  return m[1]
    .split("/")
    .map((segment) => decodePathSegment(segment).trim())
    .filter(Boolean)
    .slice(0, 3);
}

export function adminUserIdFromPath(pathname: unknown, routePrefix: unknown = ""): number | null {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/users\/(-?\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminPaymentIdFromPath(
  pathname: unknown,
  routePrefix: unknown = ""
): number | null {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/payments\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminPaymentsUserIdFromPath(
  pathname: unknown,
  routePrefix: unknown = ""
): number | null {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/payments\/users\/(-?\d+)$/);
  return m ? Number(m[1]) : null;
}

export function supportTicketIdFromPath(
  pathname: unknown,
  routePrefix: unknown = ""
): number | null {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/support\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminSupportTicketIdFromPath(
  pathname: unknown,
  routePrefix: unknown = ""
): number | null {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/support\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function syncSectionPath(
  section: unknown,
  replace = false,
  adminSection: string | null = null,
  adminUserId: AdminUserRouteId = null,
  routePrefix = ""
): void {
  if (window.location.protocol === "file:") return;
  const normalized = normalizeSection(section);
  let targetPath = APP_SECTION_PATHS[normalized] || APP_SECTION_PATHS.home;
  if (normalized === "admin") {
    const adm =
      adminSection || adminSectionFromPath(window.location.pathname, routePrefix) || "stats";
    const clearAdminUser = adminUserId === 0 || adminUserId === false;
    const uid: string | number | null =
      clearAdminUser || adminUserId === true
        ? null
        : (adminUserId ??
          (adm === "users" ? adminUserIdFromPath(window.location.pathname, routePrefix) : null));
    const supportTicketId =
      adm === "support"
        ? adminSupportTicketIdFromPath(window.location.pathname, routePrefix)
        : null;
    const paymentId =
      adm === "payments" ? adminPaymentIdFromPath(window.location.pathname, routePrefix) : null;
    const paymentUserId =
      adm === "payments" && !clearAdminUser
        ? adminPaymentsUserIdFromPath(window.location.pathname, routePrefix)
        : null;
    const settingsPath =
      adm === "settings" ? adminSettingsPathFromPath(window.location.pathname, routePrefix) : [];
    if (adm === "users" && uid) targetPath = `/admin/users/${uid}`;
    else if (adm === "support" && supportTicketId) targetPath = `/admin/support/${supportTicketId}`;
    else if (adm === "payments" && paymentUserId)
      targetPath = `/admin/payments/users/${paymentUserId}`;
    else if (adm === "payments" && paymentId) targetPath = `/admin/payments/${paymentId}`;
    else if (adm === "settings" && settingsPath.length)
      targetPath = `/admin/settings/${settingsPath.map(encodeURIComponent).join("/")}`;
    else targetPath = `/admin/${adm}`;
  }
  targetPath = withRoutePrefix(targetPath, routePrefix);
  if (window.location.pathname === targetPath) return;
  const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
  window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
}
