import { render } from "svelte/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import en from "../../../../locales/en.json";
import ru from "../../../../locales/ru.json";
import type { ApiClient } from "$lib/webapp/publicApi";
import SecurityScreen from "../screens/SecurityScreen.svelte";
import AuthScreen from "./AuthScreen.svelte";

const locale: Record<string, string> = en;
const t = (key: string, params: Record<string, unknown> = {}) =>
  (locale[key] || key).replace("{provider}", String(params.provider || ""));
const action = () => {};
afterEach(() => vi.unstubAllGlobals());

function installBrowser(initData: string) {
  vi.stubGlobal("window", {
    location: { origin: "https://shop.example", hash: "" },
    Telegram: { WebApp: { initData } },
  });
}

describe("external OAuth browser guidance", () => {
  it.each([false, true])(
    "security keeps linked identities and protects Mini App links: %s",
    (miniApp) => {
      installBrowser(miniApp ? "signed-data" : "");
      const html = render(SecurityScreen, {
        props: {
          api: vi.fn() as ApiClient["api"],
          authProviders: ["google", "yandex", "discord"],
          goSettings: action,
          linkTelegramAccount: action,
          openLinkEmailDialog: action,
          openSetPasswordDialog: action,
          t,
          telegramMiniAppContext: miniApp,
          user: {
            external_identities: [
              { provider: "google", email: "linked@example.com", can_unlink: true },
            ],
          },
        },
      }).body;
      expect(html).toContain("linked@example.com");
      expect(html.includes("data-external-oauth-browser-hint")).toBe(miniApp);
      if (miniApp) {
        expect(html).toContain(locale.wa_external_oauth_link_in_browser);
        const linkRows = (html.match(/<button\b[^>]*>[\s\S]*?<\/button>/g) || []).filter((row) =>
          row.includes(locale.wa_external_oauth_link_in_browser)
        );
        expect(linkRows).toHaveLength(2);
        for (const row of linkRows) expect(row.slice(0, row.indexOf(">"))).toContain("disabled");
        expect(html).not.toContain(">Link account</small>");
      } else {
        expect(html).toContain(locale.wa_security_link_provider);
      }
    }
  );

  it.each([
    [false, ["telegram", "google", "yandex", "discord"]],
    [true, ["telegram", "google", "yandex", "discord"]],
    [false, []],
    [true, []],
  ] as const)("login filters external providers in Mini App: %s, %j", (miniApp, providers) => {
    installBrowser(miniApp ? "signed-data" : "");
    const html = render(AuthScreen, {
      props: {
        CFG: {
          authProviders: [...providers],
          emailAuthEnabled: false,
          pluginLoginProviders: [
            { id: "work:sso", name: "Work & SSO", startPath: "/auth/plugins/work/sso/start" },
          ],
        },
        clearLoginEmailError: action,
        loginWithEmailPassword: action,
        onBackToLogin: action,
        openExternalLink: action,
        openTelegramLogin: action,
        requestEmailCode: action,
        setPasswordLoginMode: action,
        submitEmailOnEnter: action,
        verifyEmailCode: action,
        t,
      },
    }).body;
    for (const provider of providers) {
      expect(html.includes(`data-auth-provider="${provider}"`)).toBe(
        provider === "telegram" || !miniApp
      );
    }
    expect(html.includes('data-auth-provider="work:sso"')).toBe(!miniApp);
    expect(html.includes("Continue with Work &amp; SSO")).toBe(!miniApp);
    expect(html.includes("data-external-oauth-browser-hint")).toBe(miniApp);
    expect(html.includes(locale.wa_plugin_login_browser_hint)).toBe(miniApp);
  });

  it("ships browser guidance in both base locales", () => {
    for (const key of [
      "wa_external_oauth_browser_hint",
      "wa_external_oauth_open_browser",
      "wa_external_oauth_link_in_browser",
      "wa_plugin_login_browser_hint",
    ]) {
      expect((en as Record<string, string>)[key]).toBeTruthy();
      expect((ru as Record<string, string>)[key]).toBeTruthy();
    }
  });
});
