import { describe, expect, it } from "vitest";

import {
  deviceLimitReached,
  devicesCountLabel,
  devicesLimitLabel,
  devicesPercent,
  hasFiniteDeviceLimit,
} from "./devicesLabels.js";

const t = (key: string, vars: Record<string, unknown> = {}, fallback = ""): string => {
  if (key === "wa_devices_count") return `${String(vars.current)}/${String(vars.max)}`;
  if (key === "wa_devices_unlimited") return "Unlimited";
  return fallback || key;
};

describe("devicesLabels", () => {
  it("shows a pending placeholder when the device limit is unknown", () => {
    expect(devicesLimitLabel(null, t)).toBe("...");
  });

  it("prefers the subscription limit fallback over an empty devices payload", () => {
    expect(devicesLimitLabel(null, t, 5)).toBe("5");
    expect(devicesCountLabel({ current_devices: 2 }, t, 5)).toBe("2/5");
    expect(devicesPercent({ current_devices: 2 }, 5)).toBe(40);
  });

  it("treats a zero limit as unlimited", () => {
    expect(devicesLimitLabel({ max_devices: 0 }, t)).toBe("Unlimited");
    expect(devicesPercent({ current_devices: 2, max_devices: 0 })).toBe(100);
  });

  it("recognizes only positive finite device limits", () => {
    expect(hasFiniteDeviceLimit({ max_devices: 3 })).toBe(true);
    expect(hasFiniteDeviceLimit({ max_devices: 0 })).toBe(false);
    expect(hasFiniteDeviceLimit({ max_devices: null })).toBe(false);
    expect(hasFiniteDeviceLimit({}, "invalid")).toBe(false);
  });

  it("reports an exhausted limit from the count or loaded device list", () => {
    expect(deviceLimitReached({ current_devices: 3, max_devices: 3 })).toBe(true);
    expect(deviceLimitReached({ current_devices: 4, max_devices: 3 })).toBe(true);
    expect(deviceLimitReached({ current_devices: 2, max_devices: 3 })).toBe(false);
    expect(deviceLimitReached({ devices: [{}, {}] }, 2)).toBe(true);
  });

  it("does not report unknown or unlimited limits as exhausted", () => {
    expect(deviceLimitReached({ current_devices: 10, max_devices: 0 })).toBe(false);
    expect(deviceLimitReached({ current_devices: 10, max_devices: null })).toBe(false);
    expect(deviceLimitReached(null, 3)).toBe(false);
  });
});
