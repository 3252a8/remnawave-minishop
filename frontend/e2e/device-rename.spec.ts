import { expect, test } from "@playwright/test";

for (const width of [1280, 390]) {
  test(`device names can be saved, restored and cancelled at ${width}`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/app/?screen=devices&theme_preview=dark");
    await expect(page.locator(".devices-progress")).toHaveAttribute("data-state", "available");
    const card = page.locator(".device-card").first();
    const rename = card.getByRole("button", { name: "Переименовать", exact: true });
    const dialog = page.getByRole("dialog", { name: "Название устройства", exact: true });
    const input = dialog.getByRole("textbox", { name: "Название устройства", exact: true });
    const original = await card.locator(".device-name-row strong").innerText();

    await rename.click();
    await input.fill("x".repeat(33));
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toContainText("Слишком длинное название");
    await expect(dialog).toBeVisible();

    const name = "Work <laptop>";
    await input.fill(name + "\u202e\u200b");
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(card.locator(".device-name-row strong")).toContainText(name);
    await expect(card.locator(".device-card-head small")).toBeVisible();

    await rename.click();
    await expect(input).toHaveValue(name);
    await input.fill("Unsaved name");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(card.locator(".device-name-row strong")).toContainText(name);

    await rename.click();
    await input.fill("x".repeat(32));
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(rename).toBeInViewport();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
    ).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: testInfo.outputPath(`device-name-${width}.png`),
      fullPage: true,
    });

    await rename.click();
    await page.screenshot({
      path: testInfo.outputPath(`device-name-dialog-${width}.png`),
      fullPage: true,
    });
    await dialog.getByRole("button", { name: "Вернуть стандартное название", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(card.locator(".device-name-row strong")).toHaveText(original);
    expect(errors).toEqual([]);
  });

  test(`device progress updates after refresh and disconnect at ${width}`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/app/?screen=devices&theme_preview=dark&mock=devices");
    const progress = page.locator(".devices-progress");
    const status = page.locator(".devices-progress-status");
    await expect(progress).toHaveAttribute("data-state", "reached");
    await expect(progress).toHaveAttribute("aria-valuenow", "100");
    await expect(progress).toHaveAttribute("aria-valuetext", /Лимит устройств исчерпан/);
    await expect(status).toContainText("Лимит устройств исчерпан");
    const reachedColor = await progress
      .locator("span")
      .evaluate((node) => getComputedStyle(node).backgroundImage);
    await page.getByRole("button", { name: "Обновить устройства", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Обновить устройства", exact: true })
    ).toBeEnabled();
    await expect(progress).toHaveAttribute("data-state", "reached");
    await page.screenshot({
      path: testInfo.outputPath(`device-limit-${width}.png`),
      fullPage: true,
    });

    await page
      .locator(".device-card")
      .first()
      .getByRole("button", { name: "Отключить устройство", exact: true })
      .click();
    const dialog = page.locator(".webapp-device-disconnect-dialog");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Отключить", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(progress).toHaveAttribute("data-state", "available");
    await expect(progress).toHaveAttribute("aria-valuenow", "83");
    await expect(progress).toHaveAttribute("aria-valuetext", "Есть свободные места для устройств");
    await expect(status).toHaveText("Есть свободные места для устройств");
    const availableColor = await progress
      .locator("span")
      .evaluate((node) => getComputedStyle(node).backgroundImage);
    expect(availableColor).not.toBe(reachedColor);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
    ).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: testInfo.outputPath(`device-available-${width}.png`),
      fullPage: true,
    });

    await page.getByRole("button", { name: "Обновить устройства", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Обновить устройства", exact: true })
    ).toBeEnabled();
    await expect(progress).toHaveAttribute("data-state", "available");
    expect(errors).toEqual([]);
  });
}
