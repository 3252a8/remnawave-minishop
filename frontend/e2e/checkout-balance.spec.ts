import { expect, test } from "@playwright/test";

for (const width of [390, 1280]) {
  for (const funding of ["partial", "full"]) {
    test(`${funding} balance checkout at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto(`/demo/runtime/home?mock=checkout-balance-${funding}&theme_preview=dark`);
      await page.locator('[data-webapp-action="open-payment"]:visible').first().click();
      const dialog = page.locator(".dialog-card.webapp-payment-dialog");
      await expect(dialog).toBeVisible();
      const tariffs = dialog.locator(".tariff-row");
      if (await tariffs.count()) {
        await tariffs.first().click();
        await dialog.locator(".payment-submit-button").first().click();
      }
      const picker = dialog.locator(".payment-method-select-trigger");
      await expect(picker).toContainText("Tribute");
      await dialog.locator('.balance-discount [role="checkbox"]').click();
      if (funding === "partial") {
        await expect(picker).toContainText("СБП");
        await picker.click();
        await expect(page.getByRole("option", { name: "Tribute", exact: true })).toHaveCount(0);
        await page.keyboard.press("Escape");
      } else {
        await expect(picker).toHaveCount(0);
        await expect(dialog).toContainText("Внешняя оплата не требуется");
      }
      await expect(dialog.locator(".payment-submit-button").last()).toBeEnabled();
      await dialog.locator(".balance-source-trigger").click();
      await page.getByRole("option", { name: /Партнёрский баланс/ }).click();
      await expect(dialog.locator(".balance-source-trigger")).toContainText("баланса партнёрки");
      if (funding === "partial") await expect(picker).toContainText("СБП");
      else await expect(picker).toHaveCount(0);
      await expect(dialog.locator(".payment-submit-button").last()).toBeEnabled();
      expect(errors).toEqual([]);
    });
  }
}
