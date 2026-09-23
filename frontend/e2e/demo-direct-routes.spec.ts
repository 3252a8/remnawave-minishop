import { expect, test } from "@playwright/test";
import { demoAdminRoutes } from "../../docs-site/src/lib/demoRoutes.mjs";

test("every admin demo section boots from its direct runtime URL", async ({ page }) => {
  const errors: string[] = [];
  let route = "";
  page.on("pageerror", (error) => errors.push(`${route}: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" && !/favicon|telegram\.org/i.test(message.text())) {
      errors.push(`${route}: ${message.text()}`);
    }
  });

  for (const id of demoAdminRoutes) {
    route = id;
    const response = await page.goto(`/demo/runtime/admin/${id}`);
    expect(response?.status(), `HTTP status for ${id}`).toBe(200);
    await expect(
      page.locator(`.admin-section-stage[data-admin-active-section="${id}"]:not([inert])`),
      `active section for ${id}`
    ).toBeVisible();
    if (id === "plugins") {
      await expect(page.locator(".admin-list-toolbar-summary strong")).toHaveText("0");
    }
    await page.waitForTimeout(500);
    expect(errors, `browser errors after opening ${id}`).toEqual([]);
  }
});
