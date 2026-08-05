type DevicesData = Record<string, unknown> | null | undefined;
type TranslateFn = (key: string, vars?: Record<string, unknown>, fallback?: string) => string;

function devicesCount(devicesData: DevicesData): number {
  const devices = devicesData?.devices;
  return Array.isArray(devices) ? devices.length : 0;
}

export function devicesLimitLabel(
  devicesData: DevicesData,
  t: TranslateFn,
  maxDevicesOverride?: unknown
): string {
  const value = maxDevicesOverride !== undefined ? maxDevicesOverride : devicesData?.max_devices;
  if (value === undefined || value === null || value === "") {
    return t("wa_devices_limit_pending", {}, "...");
  }
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric) || numeric <= 0) return t("wa_devices_unlimited");
  return String(Math.trunc(numeric));
}

export function devicesCountLabel(
  devicesData: DevicesData,
  t: TranslateFn,
  maxDevicesOverride?: unknown
): string {
  const current = Number(devicesData?.current_devices ?? devicesCount(devicesData));
  return t("wa_devices_count", {
    current,
    max: devicesLimitLabel(devicesData, t, maxDevicesOverride),
  });
}

export function devicesPercent(devicesData: DevicesData, maxDevicesOverride?: unknown): number {
  const current = Number(devicesData?.current_devices ?? devicesCount(devicesData));
  const maxValue = maxDevicesOverride !== undefined ? maxDevicesOverride : devicesData?.max_devices;
  if (maxValue === undefined || maxValue === null || maxValue === "") return 0;
  const max = Number(maxValue || 0);
  if (!max || max <= 0) return 100;
  return Math.max(0, Math.min(100, Math.round((current / max) * 100)));
}
