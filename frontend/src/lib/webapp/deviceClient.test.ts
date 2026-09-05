import { describe, expect, it } from "vitest";

import { deviceClientLabel } from "./deviceClient.js";

describe("deviceClientLabel", () => {
  it.each([
    ["INCY/2.5.5", "Incy 2.5.5"],
    ["RabbitHole/185", "RabbitHole 185"],
    ["koala-clash/1.2.0", "Koala Clash 1.2.0"],
    ["v2RayTun", "v2RayTun"],
    ["Mihomo/1.19.27", "Mihomo 1.19.27"],
    ["clash.meta/1.19.27", "Mihomo 1.19.27"],
    ["Mihomo Meta v1.19.14 windows amd64", "Mihomo 1.19.14"],
    ["Streisand/1.6 CFNetwork", "Streisand 1.6"],
    ["v2rayNG/1.9.35", "v2rayNG 1.9.35"],
  ])("formats %s as %s", (userAgent, expected) => {
    expect(deviceClientLabel(userAgent)).toBe(expected);
  });

  it("keeps an unknown product compact instead of exposing the complete user agent", () => {
    expect(deviceClientLabel("Custom.Client/2026.4 extra metadata")).toBe("Custom.Client 2026.4");
    expect(deviceClientLabel("Mozilla/5.0 (Linux; Android 15)")).toBe("Mozilla 5.0");
  });

  it("returns an empty label when the user agent is missing", () => {
    expect(deviceClientLabel(null)).toBe("");
    expect(deviceClientLabel("   ")).toBe("");
  });
});
