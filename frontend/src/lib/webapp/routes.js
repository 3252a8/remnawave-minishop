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

export function sectionFromPath(pathname) {
  const normalizedPath = String(pathname || "")
    .trim()
    .toLowerCase()
    .replace(/\/+$/, "");
  if (!normalizedPath || normalizedPath === "/") return "home";
  if (normalizedPath === "/admin" || normalizedPath.startsWith("/admin/")) return "admin";
  if (normalizedPath === "/support" || normalizedPath.startsWith("/support/")) return "support";
  const section = normalizedPath.startsWith("/") ? normalizedPath.slice(1) : normalizedPath;
  return normalizeSection(section);
}

export function publicInstallTokenFromPath(pathname) {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  const match = normalized.match(/^\/s\/([a-f0-9]{32})$/i);
  return match ? match[1].toLowerCase() : "";
}

export function adminSectionFromPath(pathname) {
  const normalized = String(pathname || "")
    .toLowerCase()
    .replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/([a-z0-9_-]+)(?:\/.*)?$/);
  return normalizeAdminSection(m ? m[1] : "");
}

export function adminUserIdFromPath(pathname) {
  const normalized = String(pathname || "")
    .toLowerCase()
    .replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/users\/(-?\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminPaymentIdFromPath(pathname) {
  const normalized = String(pathname || "")
    .toLowerCase()
    .replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/payments\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminPaymentsUserIdFromPath(pathname) {
  const normalized = String(pathname || "")
    .toLowerCase()
    .replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/payments\/users\/(-?\d+)$/);
  return m ? Number(m[1]) : null;
}

export function supportTicketIdFromPath(pathname) {
  const normalized = String(pathname || "")
    .toLowerCase()
    .replace(/\/+$/, "");
  const m = normalized.match(/^\/support\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function adminSupportTicketIdFromPath(pathname) {
  const normalized = String(pathname || "")
    .toLowerCase()
    .replace(/\/+$/, "");
  const m = normalized.match(/^\/admin\/support\/(\d+)$/);
  return m ? Number(m[1]) : null;
}

export function syncSectionPath(section, replace = false, adminSection = null, adminUserId = null) {
  if (window.location.protocol === "file:") return;
  const normalized = normalizeSection(section);
  let targetPath = APP_SECTION_PATHS[normalized] || APP_SECTION_PATHS.home;
  if (normalized === "admin") {
    const adm = adminSection || adminSectionFromPath(window.location.pathname) || "stats";
    const uid =
      adminUserId ?? (adm === "users" ? adminUserIdFromPath(window.location.pathname) : null);
    const supportTicketId =
      adm === "support" ? adminSupportTicketIdFromPath(window.location.pathname) : null;
    const paymentId = adm === "payments" ? adminPaymentIdFromPath(window.location.pathname) : null;
    const paymentUserId =
      adm === "payments" ? adminPaymentsUserIdFromPath(window.location.pathname) : null;
    if (adm === "users" && uid) targetPath = `/admin/users/${uid}`;
    else if (adm === "support" && supportTicketId) targetPath = `/admin/support/${supportTicketId}`;
    else if (adm === "payments" && paymentUserId)
      targetPath = `/admin/payments/users/${paymentUserId}`;
    else if (adm === "payments" && paymentId) targetPath = `/admin/payments/${paymentId}`;
    else targetPath = `/admin/${adm}`;
  }
  if (window.location.pathname === targetPath) return;
  const nextUrl = `${targetPath}${window.location.search}${window.location.hash}`;
  window.history[replace ? "replaceState" : "pushState"](null, "", nextUrl);
}
