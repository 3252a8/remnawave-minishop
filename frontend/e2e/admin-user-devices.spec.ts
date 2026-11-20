import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`admin removes one selected device at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      "/demo/runtime/admin/users/ms_100000000000400080000000000de2b2?theme_preview=dark"
    );
    const card = page.locator(".admin-user-detail-page");
    const usage = card.getByRole("button", { name: /^Открыть устройства,/ });
    if (width === 390) await usage.click();
    else {
      await usage.focus();
      await usage.press("Enter");
    }
    const tab = card.getByRole("tab", { name: "Устройства", exact: true });
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(tab).toBeFocused();
    await expect(tab).toBeInViewport();
    const panel = card.getByRole("tabpanel", { name: "Устройства" });
    const rows = panel.locator("tbody tr");
    await expect(rows.nth(1)).toBeVisible();
    const apps = panel.locator('td[data-label="Приложение подключения"]');
    await expect(apps.nth(0)).toHaveText("Streisand 1.6");
    await expect(apps.nth(1)).toHaveText("Happ 3.1.0");
    const total = await rows.count();
    const first = await rows.first().locator("strong").innerText();
    const second = await rows.nth(1).locator("strong").innerText();
    const remove = rows.first().getByRole("button", { name: `Удалить ${first}` });
    await remove.click();
    const dialog = page.getByRole("dialog", { name: "Удалить устройство?" });
    await expect(dialog).toContainText(first);
    await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(remove).toBeFocused();
    await expect(rows).toHaveCount(total);
    await remove.click();
    await dialog.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(rows).toHaveCount(total - 1);
    await panel.getByRole("button", { name: "Обновить" }).click();
    await expect(rows.first().locator("strong")).toHaveText(second);
    await expect(
      card.locator(".admin-user-stat").filter({ hasText: "HWID-устройства" })
    ).toContainText(`${total - 1} / 6`);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
  });
}
