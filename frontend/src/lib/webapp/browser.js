export function readJsonScript(id) {
  const node = document.getElementById(id);
  if (!node || !node.textContent) return null;
  try {
    return JSON.parse(node.textContent);
  } catch (error) {
    console.warn(`Failed to parse JSON config from #${id}`, error);
    return null;
  }
}

export function structuredCloneSafe(value) {
  try {
    return structuredClone(value);
  } catch {
    return JSON.parse(JSON.stringify(value));
  }
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Default project logo, served by the backend when no custom logo is set.
export const DEFAULT_BRAND_TITLE = "Subscription";
export const DEFAULT_LOGO_URL = "/webapp-default-logo.webp";

export function normalizeBrand(brand = {}) {
  return {
    title: String(brand.title || DEFAULT_BRAND_TITLE).trim() || DEFAULT_BRAND_TITLE,
    logoUrl: String(brand.logoUrl || "").trim() || DEFAULT_LOGO_URL,
  };
}

export function brandFaviconHref(brand = {}) {
  return normalizeBrand(brand).logoUrl;
}

export function applyFavicon(brand = {}) {
  if (typeof document === "undefined") return;
  const favicon = document.getElementById("app-favicon");
  if (!favicon) return;

  const href = brandFaviconHref(brand);
  favicon.setAttribute("href", href);
  if (href.endsWith(".gif")) {
    favicon.setAttribute("type", "image/gif");
  } else if (href.endsWith(".webp")) {
    favicon.setAttribute("type", "image/webp");
  } else {
    favicon.removeAttribute("type");
  }
}

export function applyDocumentTitle(title) {
  if (typeof document === "undefined") return;
  const nextTitle = String(title || "").trim();
  if (!nextTitle || document.title === nextTitle) return;
  document.title = nextTitle;
}
