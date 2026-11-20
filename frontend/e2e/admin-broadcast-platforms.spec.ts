import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`broadcast targets registered iOS devices at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/broadcast?theme_preview=dark");
    const trigger = page.locator(".broadcast-audience-control .admin-select-trigger");
    await trigger.click();
    const ios = page.getByRole("option", { name: /^iOS \([1-9]\d*\)$/ });
    await expect(ios).toBeVisible();
    await expect(page.getByRole("option", { name: /^Android \([1-9]\d*\)$/ })).toBeVisible();
    await expect(
      page.getByText("Платформа зарегистрированного устройства", { exact: true })
    ).toBeVisible();
    await ios.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`audience-platforms-${width}.png`) });
    const label = await ios.innerText();
    const recipients = label.match(/\((\d+)\)/)?.[1];
    await ios.click();
    await expect(page).toHaveURL(/broadcast_target=platform%3Aios/);
    await page.reload();
    await expect(trigger).toContainText(label.trim());
    const message = "Обновление клиента для iOS";
    await page.locator(".ProseMirror").fill(message);
    await page.getByRole("button", { name: "Поставить в очередь" }).click();
    const row = page.locator(".broadcast-history-row").filter({ hasText: message });
    await expect(row).toContainText("iOS");
    await row.click();
    const detail = page.getByRole("dialog");
    await expect(
      detail.locator("dl > div").filter({ hasText: "Получателей" }).locator("dd")
    ).toHaveText(recipients!);
  });
}
