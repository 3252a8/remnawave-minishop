import { describe, expect, it } from "vitest";

import { resolveDeviceShape } from "./deviceGlyph.js";

describe("resolveDeviceShape", () => {
  it("uses Core classification independently of user-assigned names", () => {
    expect(resolveDeviceShape({ device_type: "router", display_name: "iPhone" })).toBe("router");
    expect(resolveDeviceShape({ device_type: "phone", display_name: "OpenWrt router" })).toBe(
      "phone"
    );
    expect(resolveDeviceShape({ device_type: "unknown", display_name: "OpenWrt router" })).toBe(
      "phone"
    );
  });

  it.each([
    "OpenWrt",
    "KeeneticOS",
    "NDMS",
    "MikroTik",
    "RouterOS",
    "DD-WRT",
    "AsusWRT-Merlin",
    "FreshTomato",
  ])("recognizes %s in older payloads before the Linux fallback", (platform) =>
    expect(resolveDeviceShape({ platform, user_agent: "Linux" })).toBe("router")
  );

  it("does not use a renamed title when the original model is available", () => {
    expect(resolveDeviceShape({ device_model: "iPhone", display_name: "OpenWrt" })).toBe("phone");
  });

  it("reads the form factor from the model", () => {
    expect(resolveDeviceShape({ display_name: "iPhone 15 Pro" })).toBe("phone");
    expect(resolveDeviceShape({ display_name: "MacBook Air" })).toBe("laptop");
    expect(resolveDeviceShape({ display_name: "iPad Pro" })).toBe("tablet");
    expect(resolveDeviceShape({ display_name: "Windows Laptop" })).toBe("laptop");
    expect(resolveDeviceShape({ display_name: "Ubuntu Desktop" })).toBe("desktop");
  });

  it("prefers Android over the Linux its user agent advertises", () => {
    expect(
      resolveDeviceShape({
        display_name: "Pixel 9",
        platform: "android",
        user_agent: "Mozilla/5.0 (Linux; Android 15; Pixel 9)",
      })
    ).toBe("phone");
  });

  it("keeps an iPad a tablet even though its user agent claims Macintosh", () => {
    expect(
      resolveDeviceShape({
        display_name: "iPad Air",
        user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
      })
    ).toBe("tablet");
  });

  it("treats a bare Mac as a computer rather than a phone", () => {
    expect(resolveDeviceShape({ platform: "macos", os_version: "15.4" })).toBe("laptop");
  });

  it("only matches whole words, so unrelated text keeps the phone fallback", () => {
    expect(resolveDeviceShape({ display_name: "Studios Notepad", user_agent: "Happ/3.1.0" })).toBe(
      "phone"
    );
    expect(resolveDeviceShape(null)).toBe("phone");
  });

  it("falls back to the usual shape for each platform", () => {
    expect(resolveDeviceShape({ platform: "windows" })).toBe("laptop");
    expect(resolveDeviceShape({ platform: "android" })).toBe("phone");
    expect(resolveDeviceShape({ platform: "linux" })).toBe("desktop");
  });
});
