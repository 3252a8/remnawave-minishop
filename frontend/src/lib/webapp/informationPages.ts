import { builtApiPath, type BuiltApiPath } from "./publicApi.js";

const DOCUMENT_SLUG_SEGMENT_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
const MAX_DOCUMENT_SLUG_LENGTH = 256;
const LEGACY_PAGE_SEGMENT_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;
const RESERVED_PAGE_ROOTS = new Set([
  "admin",
  "api",
  "auth",
  "checkout",
  "devices",
  "docs",
  "favicon.ico",
  "fonts",
  "health",
  "home",
  "icon-192.png",
  "icon-512.png",
  "install",
  "invite",
  "login",
  "open-app",
  "partner",
  "plans",
  "robots.txt",
  "s",
  "settings",
  "status",
  "subscription_webapp.css",
  "subscription_webapp.js",
  "support",
  "trial",
  "unsubscribe",
  "webapp-favicon",
  "webapp-default-logo.webp",
  "webapp-logo",
  "webapp-theme-assets",
  "webapp-theme-css",
  "webapp-uploaded-logo",
]);

export type PublicInformationDocument = {
  groupTitle: string;
  role: "none" | "privacy_policy" | "user_agreement";
  showInSettings: boolean;
  showInSidebar: boolean;
  slug: string;
  sortOrder: number;
  title: string;
};

export type InformationPageNavigationGroup = {
  documents: PublicInformationDocument[];
  title: string;
};

/** Converts the flat API payload to the UI model and discards malformed entries. */
export function publicInformationDocuments(value: unknown): PublicInformationDocument[] {
  const rawDocuments =
    value && typeof value === "object" && "documents" in value
      ? (value as { documents?: unknown }).documents
      : value;
  if (!Array.isArray(rawDocuments)) return [];

  return rawDocuments
    .map((document): PublicInformationDocument | null => {
      if (!document || typeof document !== "object") return null;
      const raw = document as Record<string, unknown>;
      const slug = String(raw.slug || "")
        .trim()
        .toLowerCase();
      const title = String(raw.title || "").trim();
      if (!isDocumentSlug(slug) || !title) return null;
      return {
        slug,
        title,
        groupTitle: String(raw.group_title || "").trim(),
        role: raw.role === "privacy_policy" || raw.role === "user_agreement" ? raw.role : "none",
        showInSettings: raw.show_in_settings === true,
        showInSidebar: raw.show_in_sidebar === true,
        sortOrder: Number.isFinite(Number(raw.sort_order)) ? Number(raw.sort_order) : 0,
      };
    })
    .filter((document): document is PublicInformationDocument => document !== null)
    .sort(
      (left, right) =>
        left.sortOrder - right.sortOrder ||
        left.title.localeCompare(right.title, undefined, { sensitivity: "base" }) ||
        left.slug.localeCompare(right.slug)
    );
}

export function sidebarInformationDocumentGroups(
  documents: ReadonlyArray<PublicInformationDocument>
): InformationPageNavigationGroup[] {
  const groups = new Map<string, PublicInformationDocument[]>();
  for (const document of documents) {
    if (!document.showInSidebar) continue;
    const title = document.groupTitle;
    groups.set(title, [...(groups.get(title) || []), document]);
  }
  return [...groups.entries()].map(([title, groupedDocuments]) => ({
    title,
    documents: groupedDocuments,
  }));
}

export function settingsInformationDocuments(
  documents: ReadonlyArray<PublicInformationDocument>
): PublicInformationDocument[] {
  return documents.filter((document) => document.showInSettings);
}

export function hasInformationDocumentRole(
  documents: ReadonlyArray<PublicInformationDocument>,
  role: PublicInformationDocument["role"]
): boolean {
  return role !== "none" && documents.some((document) => document.role === role);
}

export function documentSlugFromLocation(pathname: unknown): string | null {
  const normalized = String(pathname || "")
    .trim()
    .replace(/\/+$/, "");
  const legacyMatch = normalized.match(/^\/docs\/([a-z0-9][a-z0-9-]{0,63})$/);
  if (legacyMatch) return legacyMatch[1];
  if (normalized.startsWith("/docs/")) {
    const legacySlug = normalized.slice("/docs/".length);
    return isDocumentSlug(legacySlug) ? legacySlug : null;
  }
  const slug = normalized.replace(/^\/+/, "");
  return isDocumentSlug(slug) && !RESERVED_PAGE_ROOTS.has(slug.split("/", 1)[0]) ? slug : null;
}

function isDocumentSlug(slug: string): boolean {
  const segments = slug.split("/");
  return (
    slug.length <= MAX_DOCUMENT_SLUG_LENGTH &&
    segments.every((segment) => DOCUMENT_SLUG_SEGMENT_RE.test(segment))
  );
}

/** Legacy file-backed pages remain available alongside managed documents. */
export function informationPagePathFromLocation(pathname: unknown): string | null {
  const raw =
    String(pathname || "")
      .trim()
      .replace(/\/+$/, "") || "/";
  if (!raw.startsWith("/") || raw.length > 256 || /[?#\\%]/.test(raw)) return null;
  const segments = raw.slice(1).split("/");
  if (
    !segments[0] ||
    segments.length > 8 ||
    RESERVED_PAGE_ROOTS.has(segments[0]) ||
    (segments.length === 1 && segments[0] === "legal") ||
    segments.some((segment) => !LEGACY_PAGE_SEGMENT_RE.test(segment))
  )
    return null;
  return `/${segments.join("/")}`;
}

export type DocumentApiPath = BuiltApiPath<"/api/documents/{slug}">;

function normalizedDocumentSlug(slug: string): string {
  return slug.trim().replace(/^\/+/, "");
}

export function buildDocumentApiPath(slug: string): DocumentApiPath {
  const normalizedSlug = normalizedDocumentSlug(slug);
  return builtApiPath<"/api/documents/{slug}">(
    `/documents/${normalizedSlug
      .split("/")
      .map((segment) => encodeURIComponent(segment))
      .join("/")}`
  );
}

export type InformationPageApiPath = BuiltApiPath<"/api/pages/{page_path}">;

export function buildInformationPageApiPath(pagePath: string): InformationPageApiPath {
  const encoded = pagePath
    .replace(/^\/+/, "")
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return builtApiPath<"/api/pages/{page_path}">(`/pages/${encoded}`);
}

export function documentHref(slug: string): string {
  const normalizedSlug = normalizedDocumentSlug(slug);
  const encodedSlug = normalizedSlug
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  return RESERVED_PAGE_ROOTS.has(normalizedSlug.split("/", 1)[0])
    ? `/docs/${encodedSlug}`
    : `/${encodedSlug}`;
}

/** A page with only whitespace is equivalent to a document that is not published. */
export function hasInformationPageMarkdown(markdown: unknown): markdown is string {
  return typeof markdown === "string" && markdown.trim().length > 0;
}
