import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const locales = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

async function configure(page: Page) {
  await page.addInitScript(() => {
    const browser = window as Window & { oauthOpenedUrls?: string[] };
    browser.oauthOpenedUrls = [];
    window.Telegram = {
      WebApp: {
        initData: "signed-test-data",
        platform: "android",
        ready() {},
        expand() {},
        isVersionAtLeast: () => true,
        onEvent() {},
        offEvent() {},
        openLink: (url: string) => browser.oauthOpenedUrls?.push(url),
      },
    };
  });
  await page.route("https://telegram.org/js/telegram-web-app.js*", (route) =>
    route.fulfill({ contentType: "application/javascript", body: "" })
  );
  await page.route("**/settings/security?**", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const config = {
      authProviders: ["telegram", "google", "yandex", "discord"],
      defaultLanguage: "ru",
    };
    const body = (await response.text()).replace(
      "</head>",
      `<script id="webapp-config" type="application/json">${JSON.stringify(config)}</script></head>`
    );
    await route.fulfill({ response, body });
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let response: Record<string, unknown> = { ok: true };
    if (path === "/api/auth/session")
      response = { ok: true, authenticated: true, csrf_token: "test" };
    if (path.startsWith("/api/i18n")) response = { ok: true, i18n: locales };
    if (path === "/api/me")
      response = {
        ok: true,
        user: {
          id: 42,
          language_code: "ru",
          telegram_id: 42,
          telegram_linked: true,
          is_admin: false,
          external_identities: [
            { provider: "google", email: "linked@example.com", can_unlink: true },
          ],
        },
        settings: { auth_providers: ["telegram", "google", "yandex", "discord"] },
        subscription: { active: false },
        plans: [],
        payment_methods: [],
        referral: {},
      };
    if (path === "/api/extensions/runtime") response = { ok: true, generation: 1, plugins: [] };
    if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
    if (path === "/api/account/merge/status")
      response = {
        ok: true,
        providers: ["google", "yandex", "discord"],
        provider: "yandex",
        email_available: true,
        email: "linked@example.com",
        target_confirmed: false,
      };
    if (path === "/api/account/merge/request") response = { ok: true, email_code: "123456" };
    await route.fulfill({ json: response });
  });
}

for (const width of [390, 1440]) {
  test(`Mini App external linking opens the cabinet with no session transfer at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await configure(page);
    await page.goto("/settings/security?theme_preview=dark");
    const hint = page.locator("[data-external-oauth-browser-hint]");
    await expect(hint).toBeVisible();
    await expect(page.getByText("linked@example.com", { exact: true })).toBeVisible();
    const rows = page
      .locator("button.settings-row")
      .filter({ hasText: locales.ru.wa_external_oauth_link_in_browser });
    await expect(rows).toHaveCount(2);
    for (const row of await rows.all()) await expect(row).toBeDisabled();
    const miniAppUrl = page.url();
    await hint.getByRole("button", { name: locales.ru.wa_external_oauth_open_browser }).click();
    const opened = await page.evaluate(
      () => (window as Window & { oauthOpenedUrls?: string[] }).oauthOpenedUrls
    );
    expect(opened).toEqual([`${new URL(page.url()).origin}/settings/security`]);
    expect(page.url()).toBe(miniAppUrl);
    expect(await page.locator("body").evaluate((body) => body.scrollWidth)).toBeLessThanOrEqual(
      width
    );
    await page.screenshot({
      path: testInfo.outputPath(`external-oauth-${width}.png`),
      fullPage: true,
    });
  });

  test(`Mini App merge blocks WebView OAuth and preserves email confirmation at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    await configure(page);
    await page.goto(
      "/settings/security?external_auth=yandex:account_merge_required&theme_preview=dark"
    );
    const dialog = page.locator(".account-merge-dialog");
    await expect(dialog).toBeVisible();
    for (const provider of ["Google", "Yandex", "Discord"]) {
      await expect(
        dialog.getByRole("button", { name: `Подтвердить через ${provider}`, exact: true })
      ).toBeDisabled();
    }
    await expect(dialog.locator(".account-merge-form input")).toHaveValue("123456");
    await expect(dialog.locator("[data-external-oauth-browser-hint]")).toBeVisible();
  });
}
