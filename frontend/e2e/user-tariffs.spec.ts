import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`tariff dashboard drilldown and trial filter persist at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/stats?theme_preview=dark");
    const row = page.locator('[data-admin-tariff-filter="tariff:standard"]');
    await expect(row).toBeVisible();
    const warning = page.locator(".admin-config-alerts");
    await expect(warning).toBeVisible();
    await expect
      .poll(() =>
        warning.evaluate((alert) => {
          const card = alert.parentElement?.querySelector(".admin-stats-audience-card");
          if (!alert.getClientRects().length || !card?.getClientRects().length) return -1;
          const alertBox = alert.getBoundingClientRect();
          return card.getBoundingClientRect().top - alertBox.bottom;
        })
      )
      .toBeGreaterThanOrEqual(15);
    const count = Number(
      await row.locator(".admin-tariff-distribution-number strong").textContent()
    );
    await row.click();
    await expect(page).toHaveURL(/users_filter=active_subscription/);
    await expect(page).toHaveURL(/users_tariff=tariff%3Astandard/);
    await expect(page.locator(".admin-list-toolbar-summary strong")).toHaveText(String(count));
    await page.reload();
    await expect(page.locator(".admin-list-toolbar-summary strong")).toHaveText(String(count));
    const tariffSelect = page.locator('.admin-select-trigger[aria-label="Тариф / триал"]');
    if (width < 720) await page.locator(".admin-users-filter-toggle").click();
    await tariffSelect.filter({ visible: true }).click();
    await page.getByRole("option", { name: "Триал", exact: true }).click();
    await expect(page).toHaveURL(/users_tariff=trial/);
    if (width < 720) {
      const dialog = page.locator(".admin-users-filter-dialog");
      await expect(dialog).toBeVisible();
      await dialog.getByRole("button", { name: "Готово", exact: true }).click();
    }
    const plans = page.locator(
      width < 720
        ? ".admin-users-mobile-list .admin-subscription-plan"
        : ".admin-users-cell-tariff .admin-subscription-plan"
    );
    await expect(plans.first()).toHaveText("Триал");
    await expect(page.locator(".admin-users-filter-chips")).toContainText("Триал");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(2);
    expect(errors).toEqual([]);
  });
}
