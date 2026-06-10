import { ADMIN_SECTIONS, APP_SECTION_PATHS } from "./constants.js";

export function normalizeSection(value) {
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

export function normalizeAdminSection(value) {
  const section = String(value || "")
    .trim()
    .toLowerCase();
  return ADMIN_SECTIONS.has(section) ? section : "stats";
}

function normalizePathname(pathname) {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  return normalized || "/";
}

export function stripRoutePrefix(pathname, routePrefix = "") {
  const path = normalizePathname(pathname);
  const prefix = normalizePathname(routePrefix);
  if (prefix === "/") return path;
  if (path.toLowerCase() === prefix.toLowerCase()) return "/";
  if (path.toLowerCase().startsWith(`${prefix.toLowerCase()}/`)) {
    return path.slice(prefix.length) || "/";
  }
  return path;
}

export function withRoutePrefix(pathname, routePrefix = "") {
  const path = normalizePathname(pathname);
  const prefix = normalizePathname(routePrefix);
  if (prefix === "/") return path;
  if (path === "/") return prefix;
  return `${prefix}${path}`;
}

export function sectionFromPath(pathname, routePrefix = "") {
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

export function publicInstallTokenFromPath(pathname) {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  const match = normalized.match(/^\/s\/([a-f0-9]{32})$/i);
  return match ? match[1].toLowerCase() : "";
}

export function adminSectionFromPath(pathname, routePrefix = "") {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/([a-z0-9_-]+)(?:\/.*)?$/);
  return normalizeAdminSection(m ? m[1] : "");
}

export function adminUserIdFromPath(pathname, routePrefix = "") {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/users\/(-?\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminPaymentIdFromPath(pathname, routePrefix = "") {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/payments\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminPaymentsUserIdFromPath(pathname, routePrefix = "") {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/payments\/users\/(-?\d+)$/);
  return m ? Number(m[1]) : null;
}

export function supportTicketIdFromPath(pathname, routePrefix = "") {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/support\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminSupportTicketIdFromPath(pathname, routePrefix = "") {
  const normalized = stripRoutePrefix(pathname, routePrefix).toLowerCase().replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/support\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function syncSectionPath(
  section,
  replace = false,
  adminSection = null,
  adminUserId = null,
  routePrefix = ""
) {
  if (window.location.protocol === "file:") return;
  const normalized = normalizeSection(section);
  let targetPath = APP_SECTION_PATHS[normalized] || APP_SECTION_PATHS.home;
  if (normalized === "admin") {
    const adm =
      adminSection || adminSectionFromPath(window.location.pathname, routePrefix) || "stats";
    const clearAdminUser = adminUserId === 0 || adminUserId === false;
    const uid = clearAdminUser
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
    if (adm === "users" && uid) targetPath = `/admin/users/${uid}`;
    else if (adm === "support" && supportTicketId) targetPath = `/admin/support/${supportTicketId}`;
    else if (adm === "payments" && paymentUserId)
      targetPath = `/admin/payments/users/${paymentUserId}`;
    else if (adm === "payments" && paymentId) targetPath = `/admin/payments/${paymentId}`;
    else targetPath = `/admin/${adm}`;
  }
  targetPath = withRoutePrefix(targetPath, routePrefix);
  if (window.location.pathname === targetPath) return;
  const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
  window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
}
