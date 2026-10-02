import { expect, test } from "@playwright/test";

for (const width of [1280, 390]) {
  test(`trial premium title can be saved and reset at ${width}px`, async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/tariffs?theme_preview=dark");

    const trigger = page.getByRole("button", { name: /^Пробный период/ });
    await trigger.click();
    const content = page.locator("#admin-trial-settings-content");
    const general = content.locator(".admin-settings-field-group").filter({
      has: page.getByText("Общие настройки", { exact: true }),
    });
    const titleRow = general.locator(".admin-trial-setting-row").filter({
      has: page.locator("code", { hasText: "TRIAL_PREMIUM_TITLE" }),
    });
    const input = titleRow.getByRole("textbox", {
      name: "Название premium-раздела триала",
      exact: true,
    });
    const duration = general
      .locator(".admin-trial-setting-row")
      .filter({ has: page.locator("code", { hasText: "TRIAL_DURATION_DAYS" }) })
      .getByRole("spinbutton");
    const save = content.getByRole("button", { name: "Сохранить", exact: true });

    await expect(input).toBeVisible();
    await expect(input).toHaveValue("");
    await expect(titleRow).toContainText("на языке пользователя");
    await expect(general.getByRole("spinbutton")).toHaveCount(4);
    const originalDuration = await duration.inputValue();
    const title = "Обход блокировок — пробный доступ";

    await input.fill("Не сохранено");
    await titleRow.getByRole("button", { name: "Сбросить", exact: true }).click();
    await expect(input).toHaveValue("");
    await expect(titleRow.getByRole("button", { name: "Сбросить", exact: true })).toHaveCount(0);

    await input.fill(title);
    await duration.fill(String(Number(originalDuration) + 1));
    await save.click();
    await expect(save).toHaveCount(0);
    await expect(input).toHaveValue(title);
    await trigger.click();
    await expect(content).toHaveCount(0);
    await trigger.click();
    await expect(input).toHaveValue(title);
    await expect(duration).toHaveValue(String(Number(originalDuration) + 1));

    await input.scrollIntoViewIfNeeded();
    const bounds = await input.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect(
      await general.evaluate((element) => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(2);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: testInfo.outputPath(`trial-settings-${width}.png`),
      fullPage: true,
    });

    await input.fill("");
    await duration.fill(originalDuration);
    await save.click();
    await expect(save).toHaveCount(0);
    await trigger.click();
    await expect(content).toHaveCount(0);
    await trigger.click();
    await expect(input).toHaveValue("");
    await expect(duration).toHaveValue(originalDuration);
    expect(errors).toEqual([]);
  });
}
