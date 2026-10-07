import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

import {
  deviceLimitReached,
  devicesCountLabel,
  devicesLimitLabel,
  devicesPercent,
  devicesProgressState,
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

  it("keeps rounded full progress below the limit available", () => {
    const data = { current_devices: 199, max_devices: 200 };
    expect(devicesPercent(data)).toBe(100);
    expect(devicesProgressState(data, true)).toBe("available");
    expect(devicesProgressState({ ...data, current_devices: 200 }, true)).toBe("reached");
    expect(devicesProgressState({ ...data, current_devices: 201 }, true)).toBe("reached");
  });

  it("uses the explicit limit and exact count or loaded list", () => {
    expect(devicesProgressState({ current_devices: 3, max_devices: 5 }, true, 2)).toBe("reached");
    expect(devicesProgressState({ current_devices: 2 }, true, 5)).toBe("available");
    expect(devicesProgressState({ current_devices: 0, devices: [{}, {}] }, true, 2)).toBe(
      "available"
    );
    expect(devicesProgressState({ devices: [{}, {}] }, true, 2)).toBe("reached");
    expect(devicesProgressState({ devices: [] }, true, 2)).toBe("available");
    expect(devicesProgressState({ current_devices: "3", max_devices: "3" }, true)).toBe("reached");
  });

  it("distinguishes unlimited limits from missing or invalid data", () => {
    expect(devicesProgressState({ current_devices: 100, max_devices: 0 }, true)).toBe("unlimited");
    expect(devicesProgressState({ current_devices: 100, max_devices: 3 }, true, 0)).toBe(
      "unlimited"
    );
    for (const max of [undefined, null, "", " ", "invalid", NaN, Infinity, -Infinity, false]) {
      expect(devicesProgressState({ current_devices: 3, max_devices: max }, true)).toBe("pending");
    }
    expect(devicesProgressState({ current_devices: 3, max_devices: 3 }, false)).toBe("pending");
    expect(devicesProgressState({ current_devices: 3, max_devices: 0 }, false)).toBe("pending");
    expect(devicesProgressState(null, true, 3)).toBe("pending");
    expect(devicesProgressState({}, true, 3)).toBe("pending");
    for (const current of ["", " ", "invalid", NaN, Infinity, -1, false]) {
      expect(devicesProgressState({ current_devices: current, max_devices: 3 }, true)).toBe(
        "pending"
      );
    }
  });

  it("provides localized text for every semantic state in both base locales", () => {
    for (const language of ["ru", "en"]) {
      const locale: Record<string, unknown> = JSON.parse(
        readFileSync(new URL(`../../../../locales/${language}.json`, import.meta.url), "utf8")
      );
      for (const state of ["available", "reached", "unlimited", "pending"]) {
        expect(locale[`wa_devices_progress_${state}`]).toBeTruthy();
      }
    }
  });
});
