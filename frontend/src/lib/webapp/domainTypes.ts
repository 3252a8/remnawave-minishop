import type { MeResponse } from "./publicApi";

export type WebappRecord = Record<string, unknown>;
export type WebappData = MeResponse & WebappRecord;

export type WebappBillingPlan = WebappRecord & {
  device_count?: number | string | null;
  hwid_renewal?: WebappRecord;
  months?: number | string | null;
  sale_mode?: string | null;
  tariff_key?: string | null;
  traffic_bonus_gb?: number | string | null;
  traffic_gb?: number | string | null;
};

export type WebappBillingAction = WebappRecord & {
  mode?: string | null;
  months?: number | string | null;
  traffic_gb?: number | string | null;
};

export type WebappBillingTarget = WebappRecord & {
  tariff_key?: string | null;
};

export function recordField(value: unknown): WebappRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as WebappRecord) : {};
}

export function recordOrNull(value: unknown): WebappRecord | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as WebappRecord)
    : null;
}

export function arrayField(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function recordArrayField(value: unknown): WebappRecord[] {
  return Array.isArray(value)
    ? value.filter((item): item is WebappRecord => Boolean(recordOrNull(item)))
    : [];
}

export function stringField(value: unknown): string {
  return typeof value === "string" ? value : "";
}
