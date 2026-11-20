import { jsonBody } from "../demoMockRuntime";
import { demoUserPlatforms } from "./adminBroadcasts";
import type { CloneFn, DemoAdminUser, DemoUserDetail } from "./dataset";
import { demoRegisteredDevices } from "./users";

export function adminUserResourceDemoResponse(
  resource: string,
  action: string | undefined,
  detail: DemoUserDetail,
  user: DemoAdminUser | undefined,
  maxDevices: number | null,
  options: RequestInit,
  clone: CloneFn
) {
  const method = (options.method || "GET").toUpperCase();
  if (resource === "note") {
    if (!user?.panel_user_uuid) return { ok: false, error: "panel_user_not_found" };
    const note = String(detail.panel_note || "");
    if (method === "GET") return { ok: true, note };
    if (method === "PUT") {
      const body = jsonBody(options);
      if (body.previous_note !== note) return { ok: false, error: "note_conflict" };
      detail.panel_note = String(body.note || "");
      return { ok: true, note: detail.panel_note };
    }
    return { ok: false, error: "method_not_allowed" };
  }
  if (resource === "hwid-devices") {
    const devices = demoRegisteredDevices(detail);
    if (!action && method === "GET") return { ok: true, devices: clone(devices) };
    if (method !== "POST") return { ok: false, error: "method_not_allowed" };
    if (action === "disconnect") {
      const token = jsonBody(options).device_token;
      const index = devices.findIndex((device) => device.token === token);
      if (index < 0) return { ok: false, error: "device_not_found" };
      devices.splice(index, 1);
    } else if (action === "reset") {
      devices.length = 0;
    } else {
      return { ok: false, error: "not_found" };
    }
    detail.hwid_devices = {
      current_devices: devices.length,
      max_devices: maxDevices,
    };
    return { ok: true };
  }
  if (resource === "broadcast-audiences") {
    const targets = user?.is_banned
      ? []
      : [
          "all",
          detail.active_subscription ? "active" : "inactive",
          ...demoUserPlatforms(detail).keys(),
        ];
    const existing = detail.broadcast_audience_exclusions;
    const excluded = new Set(Array.isArray(existing) ? existing.map(String) : []);
    if (method === "PATCH") {
      const { action, target } = jsonBody(options);
      if (action === "exclude" && typeof target === "string") excluded.add(target);
      if (action === "include" && typeof target === "string") excluded.delete(target);
      if (action === "exclude_all") targets.forEach((name) => excluded.add(name));
      if (action === "reset") excluded.clear();
      detail.broadcast_audience_exclusions = [...excluded];
      return { ok: true, excluded: [...excluded] };
    }
    return { ok: true, targets, excluded: [...excluded] };
  }
  return undefined;
}
