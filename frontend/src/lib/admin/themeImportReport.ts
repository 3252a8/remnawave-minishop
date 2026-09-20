export type ThemeImportFailure = {
  code: string;
  detail: string;
};

type Translate = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type ErrorPayload = Record<string, unknown>;

const ARCHIVE_CODES = new Set([
  "archive_file_required",
  "duplicate_collection_path",
  "empty_archive",
  "invalid_archive",
  "invalid_collection",
  "invalid_json",
  "invalid_theme_manifest",
  "invalid_theme_token",
  "missing_css_asset",
  "missing_css_file",
  "nested_theme_manifests",
  "no_themes_found",
  "one_archive_required",
  "zip_required",
]);
const SAFETY_CODES = new Set([
  "css_import_not_allowed",
  "external_css_url",
  "invalid_css_url",
  "unsafe_css_function",
  "unsafe_css_property",
  "unsafe_path",
  "unsupported_theme_file",
  "unsupported_zip_entry",
  "url_in_theme_token",
]);
const SIZE_CODES = new Set([
  "archive_limit",
  "archive_too_deep",
  "archive_too_large",
  "css_too_deep",
  "css_too_large",
  "image_too_large",
  "manifest_too_large",
  "theme_file_too_large",
  "too_many_files",
  "too_many_themes",
]);
const REPOSITORY_CODES = new Set([
  "invalid_repository_url",
  "repository_address_blocked",
  "repository_host_not_supported",
  "repository_not_found",
  "repository_ref_ambiguous",
  "repository_ref_not_found",
  "repository_url_not_supported",
  "subdirectory_not_found",
]);
const TEMPORARY_CODES = new Set([
  "import_interrupted",
  "repository_rate_limited",
  "repository_unavailable",
  "themes_busy",
  "too_many_imports",
]);
const COMPATIBILITY_CODES = new Set([
  "incompatible_overrides",
  "incompatible_theme_api",
  "theme_alias_not_allowed",
  "theme_name_too_long",
]);

function payload(value: unknown): ErrorPayload | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as ErrorPayload)
    : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

export function normalizeThemeImportFailure(value: unknown): ThemeImportFailure | null {
  const outer = payload(value);
  const nested = payload(outer?.error);
  const code =
    text(value) ||
    text(outer?.error) ||
    text(outer?.code) ||
    text(nested?.error) ||
    text(nested?.code);
  if (!code) return null;
  const detail = text(outer?.detail) || text(nested?.detail) || text(outer?.message);
  return { code, detail: detail === code ? "" : detail };
}

export function themeImportRecommendations(code: string, at: Translate): string[] {
  let recommendation: string;
  if (ARCHIVE_CODES.has(code)) {
    recommendation = at(
      "appearance_import_fix_archive",
      {},
      "Rebuild the ZIP package: keep valid theme.json files, valid JSON, and every referenced CSS or image file."
    );
  } else if (SAFETY_CODES.has(code)) {
    recommendation = at(
      "appearance_import_fix_safety",
      {},
      "Remove absolute or parent paths, symbolic links, external URLs, CSS imports, and unsafe CSS constructs."
    );
  } else if (SIZE_CODES.has(code)) {
    recommendation = at(
      "appearance_import_fix_size",
      {},
      "Reduce the archive, file count, nesting depth, or asset sizes and keep the ZIP below 20 MB."
    );
  } else if (REPOSITORY_CODES.has(code)) {
    recommendation = at(
      "appearance_import_fix_repository",
      {},
      "Use a public HTTPS GitHub or GitLab repository and verify the branch, tag, commit, and theme subdirectory."
    );
  } else if (TEMPORARY_CODES.has(code)) {
    recommendation = at(
      "appearance_import_fix_temporary",
      {},
      "Wait a little and retry. If the repository remains unavailable, download it and import a ZIP archive."
    );
  } else if (COMPATIBILITY_CODES.has(code)) {
    recommendation = at(
      "appearance_import_fix_compatibility",
      {},
      "Update the package to the supported theme API, use a unique lowercase key, and remove unsupported fields."
    );
  } else {
    recommendation = at(
      "appearance_import_fix_generic",
      {},
      "Use the error code and detail below to correct the named file or field, then create a fresh package."
    );
  }
  return [
    recommendation,
    at(
      "appearance_import_fix_retry",
      {},
      "After fixing the source, start a new import so every validation runs again."
    ),
  ];
}
