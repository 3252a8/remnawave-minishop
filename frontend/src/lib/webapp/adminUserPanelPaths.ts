import { builtApiPath } from "./publicApi";

export function buildAdminUserDevicesPath(userId: number | string) {
  return builtApiPath<"/api/admin/users/{user_id}/hwid-devices">(
    `/admin/users/${encodeURIComponent(String(userId))}/hwid-devices`
  );
}

export function buildAdminUserNotePath(userId: number | string) {
  return builtApiPath<"/api/admin/users/{user_id}/note">(
    `/admin/users/${encodeURIComponent(String(userId))}/note`
  );
}

export function buildAdminUserDisconnectDevicePath(userId: number | string) {
  return builtApiPath<"/api/admin/users/{user_id}/hwid-devices/disconnect">(
    `/admin/users/${encodeURIComponent(String(userId))}/hwid-devices/disconnect`
  );
}
