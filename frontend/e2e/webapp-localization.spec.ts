import { expect, test } from "@playwright/test";

import { DEMO_LANGUAGE_STORAGE_KEY } from "../src/lib/webapp/demoMockRuntime";

const APP_URL = "/demo/runtime/app/";

for (const language of ["ru", "en"]) {
  for (const mode of ["tariffs", "server-status"]) {
    test(`server status uses the Mini App translation in ${language} (${mode})`, async ({
      page,
    }) => {
      const appTitle = `App status ${language}`;
      const botTitle = `Bot status ${language}`;
      const contactTitle = `Admin contact ${language}`;
      await page.addInitScript(({ key, value }) => window.localStorage.setItem(key, value), {
        key: DEMO_LANGUAGE_STORAGE_KEY,
        value: language,
      });
      await page.route(
        (url) => url.pathname === APP_URL,
        async (route) => {
          const response = await route.fetch();
          const original = await response.text();
          const body = original.replace(
            /(<script id="i18n" type="application\/json">)([\s\S]*?)(<\/script>)/,
            (_match, opening: string, json: string, closing: string) => {
              const messages = JSON.parse(json) as Record<string, Record<string, string>>;
              messages[language].wa_server_status_title = appTitle;
              messages[language].menu_server_status_button = botTitle;
              messages[language].menu_support_button = contactTitle;
              return `${opening}${JSON.stringify(messages)}${closing}`;
            }
          );
          expect(body).not.toBe(original);
          await route.fulfill({ response, body });
        }
      );

      await page.goto(`${APP_URL}?path=/settings&mock=${mode}`);
      const statusButton = page.locator(".settings-row-status");
      await expect(statusButton).toHaveText(appTitle);
      await expect(page.locator(".settings-row-support")).toHaveText(contactTitle);

      if (mode === "server-status") {
        await statusButton.click();
        await expect(page.locator(".status-topbar h1")).toHaveText(appTitle);
        await page.goto(`${APP_URL}?path=/home&mock=${mode}`);
        await expect(page.locator(".server-status-card-copy strong")).toHaveText(appTitle);
      }
    });
  }
}
