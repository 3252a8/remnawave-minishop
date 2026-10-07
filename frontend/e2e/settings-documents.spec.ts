import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const locales = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};
const legacyPrivacyUrl = "https://example.test/legacy-privacy";
const legacyAgreementUrl = "https://example.test/legacy-terms";

async function configureDocuments(
  page: Page,
  language: "ru" | "en",
  documents: Record<string, unknown>[],
  status = 200
) {
  let releaseDocuments = () => {};
  const documentsReleased = new Promise<void>((resolve) => {
    releaseDocuments = resolve;
  });
  await page.route("**/demo/runtime/**", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const config = {
      authProviders: ["email"],
      emailAuthEnabled: false,
      defaultLanguage: language,
      privacyPolicyUrl: legacyPrivacyUrl,
      userAgreementUrl: legacyAgreementUrl,
    };
    const body = (await response.text()).replace(
      "</head>",
      `<script id="webapp-config" type="application/json">${JSON.stringify(config)}</script></head>`
    );
    await route.fulfill({ response, body });
  });
  await page.route("https://example.test/**", (route) =>
    route.fulfill({ contentType: "text/plain", body: "Legal document" })
  );
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/documents") {
      await documentsReleased;
      return route.fulfill({
        status,
        json: status === 200 ? { ok: true, documents } : { ok: false, error: "unavailable" },
      });
    }
    let response: Record<string, unknown> = { ok: true };
    if (path === "/api/auth/session")
      response = { ok: true, authenticated: true, csrf_token: "fixture-csrf" };
    if (path.startsWith("/api/i18n")) response = { ok: true, i18n: locales };
    if (path === "/api/me")
      response = {
        ok: true,
        user: { id: 42, language_code: language, is_admin: false },
        settings: {},
        subscription: { active: false },
        plans: [],
        payment_methods: [],
        referral: {},
      };
    if (path === "/api/extensions/runtime") response = { ok: true, generation: 1, plugins: [] };
    if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
    await route.fulfill({ json: response });
  });
  return releaseDocuments;
}

async function expectPendingDocuments(page: Page, language: "ru" | "en") {
  const loading = page.locator(".settings-documents-loading");
  await expect(loading).toHaveAttribute("role", "status");
  await expect(loading).toHaveAttribute("aria-busy", "true");
  await expect(loading).toHaveText(locales[language].wa_loading);
  await expect(page.locator(".settings-row-policy")).toHaveCount(0);
}

for (const width of [1440, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`settings wait for managed documents and keep role icons at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const releaseDocuments = await configureDocuments(page, language, [
        {
          slug: "privacy-policy",
          title: "Managed privacy",
          role: "privacy_policy",
          show_in_settings: true,
          sort_order: 2,
        },
        {
          slug: "terms",
          title: "Managed agreement",
          role: "user_agreement",
          show_in_settings: true,
          sort_order: 3,
        },
        {
          slug: "api/reference",
          title: "Additional document",
          role: "none",
          show_in_settings: true,
          sort_order: 1,
        },
        { slug: "hidden", title: "Hidden document", show_in_settings: false, sort_order: 0 },
      ]);
      await page.goto("/demo/runtime/settings?theme_preview=dark");
      await expectPendingDocuments(page, language);
      releaseDocuments();
      const rows = page.locator(".settings-row-policy");
      await expect(rows).toHaveText([
        "Additional document",
        "Managed privacy",
        "Managed agreement",
      ]);
      await expect(rows.nth(0)).toHaveAttribute("href", "/demo/runtime/docs/api/reference");
      await expect(rows.nth(1)).toHaveAttribute("href", "/demo/runtime/privacy-policy");
      await expect(rows.nth(2)).toHaveAttribute("href", "/demo/runtime/terms");
      await expect(rows.nth(0).locator("svg").first()).toHaveClass(/lucide-file-text/);
      await expect(rows.nth(1).locator("svg").first()).toHaveClass(/lucide-shield/);
      await expect(rows.nth(2).locator("svg").first()).toHaveClass(/lucide-file-text/);
      await expect(page.locator(".settings-documents-loading")).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: locales[language].wa_settings_privacy_policy })
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: locales[language].wa_settings_user_agreement })
      ).toHaveCount(0);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
      ).toBeLessThanOrEqual(1);
      await page.screenshot({
        path: testInfo.outputPath(`settings-documents-${width}-${language}.png`),
      });
      expect(errors).toEqual([]);
    });
  }
}

for (const [width, language] of [
  [390, "ru"],
  [1440, "en"],
] as const) {
  for (const [scenario, status] of [
    ["empty list", 200],
    ["older API", 404],
    ["API failure", 500],
  ] as const) {
    test(`settings resolve legacy documents after ${scenario} at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const releaseDocuments = await configureDocuments(page, language, [], status);
      await page.goto("/demo/runtime/settings?theme_preview=dark");
      await expectPendingDocuments(page, language);
      releaseDocuments();
      const agreement = page.getByRole("button", {
        name: locales[language].wa_settings_user_agreement,
        exact: true,
      });
      const privacy = page.getByRole("button", {
        name: locales[language].wa_settings_privacy_policy,
        exact: true,
      });
      await expect(page.locator(".settings-row-policy")).toHaveText([
        locales[language].wa_settings_user_agreement,
        locales[language].wa_settings_privacy_policy,
      ]);
      await expect(agreement.locator("svg").first()).toHaveClass(/lucide-file-text/);
      await expect(privacy.locator("svg").first()).toHaveClass(/lucide-shield/);
      await expect(page.locator(".settings-documents-loading")).toHaveCount(0);
      for (const [button, url] of [
        [agreement, legacyAgreementUrl],
        [privacy, legacyPrivacyUrl],
      ] as const) {
        await button.click();
        await expect(page).toHaveURL(url);
        await page.goBack();
      }
    });
  }

  test(`settings respect hidden legal roles and retain other legacy links at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 900 });
    const releaseDocuments = await configureDocuments(page, language, [
      { slug: "privacy", title: "Hidden privacy", role: "privacy_policy", show_in_settings: false },
    ]);
    await page.goto("/demo/runtime/settings?theme_preview=dark");
    await expectPendingDocuments(page, language);
    releaseDocuments();
    await expect(page.locator(".settings-row-policy")).toHaveText([
      locales[language].wa_settings_user_agreement,
    ]);
    await expect(
      page.getByRole("button", { name: locales[language].wa_settings_privacy_policy })
    ).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Hidden privacy" })).toHaveCount(0);
  });
}
