import { describe, expect, it } from "vitest";

import {
  detectInstallPlatformKey,
  installIconColorStyle,
  isUnsafeInstallUrl,
  localizedInstallValue,
  renderInstallQrDataUrl,
  resolveInstallButtonAction,
  resolveInstallTemplate,
} from "./installGuideRuntime";
import { guideDocumentToConfig } from "./guideDocument";

describe("install guide runtime helpers", () => {
  it("localizes values by the active language with fallbacks", () => {
    expect(localizedInstallValue({ en: "Install", ru: "Install ru" }, "en-US", "fallback")).toBe(
      "Install"
    );
    expect(localizedInstallValue({ ru: "Install ru" }, "de", "fallback")).toBe("Install ru");
    expect(localizedInstallValue(null, "en", "fallback")).toBe("fallback");
  });

  it("detects platform from telegram and browser hints", () => {
    expect(detectInstallPlatformKey(["ios", "android"], "ios", null)).toBe("ios");
    expect(
      detectInstallPlatformKey(["windows", "macos"], "", { userAgentData: { platform: "Win32" } })
    ).toBe("windows");
  });

  it("resolves templates and rejects unsafe links", () => {
    const resolved = resolveInstallTemplate("{{SUBSCRIPTION_LINK}}:{{USERNAME}}", {
      subscription: { config_link: "https://sub.example/link" },
      user: { username: "alice" },
    });

    expect(resolved).toBe("https://sub.example/link:alice");
    expect(installIconColorStyle("emerald")).toBe("--install-icon-color:#10b981;");
    expect(isUnsafeInstallUrl("javascript:alert(1)")).toBe(true);
    expect(isUnsafeInstallUrl("https://example.com")).toBe(false);
  });

  it("resolves button actions and shields QR rendering errors", async () => {
    const context = {
      subscription: { config_link: "https://sub.example/link" },
      user: { username: "alice" },
    };

    expect(
      resolveInstallButtonAction({ type: "copyButton", link: "{{USERNAME}}" }, context)
    ).toEqual({
      kind: "copy",
      value: "alice",
    });
    expect(resolveInstallButtonAction({ link: "{{SUBSCRIPTION_LINK}}" }, context)).toEqual({
      kind: "open",
      value: "https://sub.example/link",
    });
    await expect(
      renderInstallQrDataUrl(" https://sub.example/link ", async (link) => link)
    ).resolves.toBe("https://sub.example/link");
    await expect(
      renderInstallQrDataUrl("https://sub.example/link", async () => {
        throw new Error("qr failed");
      })
    ).resolves.toBe("");
  });

  it("renders a versioned document with a new platform and resolves resource actions", () => {
    const config = guideDocumentToConfig({
      schemaVersion: 1,
      platforms: [{ id: "routers", displayName: { en: "Routers" }, apps: [{ name: "Router" }] }],
    });
    expect(config?.platforms).toHaveProperty("routers");
    expect(
      resolveInstallButtonAction(
        {
          action: {
            kind: "open",
            target: {
              kind: "resource",
              resourceId: "primary-subscription",
              representation: "http",
            },
          },
        },
        {
          subscription: {
            link_mode: "minishop",
            http_url: "https://shop.test/s/token",
            config_link: "happ://encrypted",
          },
        }
      )
    ).toEqual({ kind: "open", value: "https://shop.test/s/token" });
  });
});
