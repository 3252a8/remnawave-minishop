import { builtApiPath } from "./publicApi";

export function buildThemeImportPath(id: string) {
  return builtApiPath<"/api/admin/themes/imports/{operation_id}">(
    `/admin/themes/imports/${encodeURIComponent(id)}`
  );
}
export function buildThemeInstallPath(id: string) {
  return builtApiPath<"/api/admin/themes/imports/{operation_id}/install">(
    `/admin/themes/imports/${encodeURIComponent(id)}/install`
  );
}
export function buildThemeLibraryItemPath(key: string) {
  return builtApiPath<"/api/admin/themes/library/{key}">(
    `/admin/themes/library/${encodeURIComponent(key)}`
  );
}
export function buildThemeRollbackPath(key: string) {
  return builtApiPath<"/api/admin/themes/library/{key}/rollback">(
    `/admin/themes/library/${encodeURIComponent(key)}/rollback`
  );
}
export function buildThemePreviewPath(key: string, variant: string, importId?: string): string {
  const prefix = importId
    ? `/admin/themes/imports/${encodeURIComponent(importId)}/preview`
    : "/admin/themes/library";
  return importId
    ? `${prefix}/${encodeURIComponent(key)}?variant=${variant}`
    : `${prefix}/${encodeURIComponent(key)}/preview?variant=${variant}`;
}

export function buildThemePreviewUploadPath(key: string) {
  return builtApiPath<"/api/admin/themes/library/{key}/preview">(
    `/admin/themes/library/${encodeURIComponent(key)}/preview`
  );
}
