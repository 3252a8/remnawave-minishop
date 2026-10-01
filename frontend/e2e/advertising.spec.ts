import { expect, test } from "@playwright/test";

for (const width of [1440, 1024, 390]) {
  test(`advertising campaign sections work at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/demo/runtime/admin/ads");
    const campaignTable = page.locator(".ads-campaign-table");
    await expect(campaignTable).toBeVisible();
    if (width === 1024) {
      const scrolling = await campaignTable.locator("..").evaluate((el) => {
        const overflows = el.scrollWidth > el.clientWidth;
        el.scrollLeft = 100;
        const moved = el.scrollLeft > 0;
        el.scrollLeft = 0;
        return { overflows, moved };
      });
      expect(scrolling).toEqual({ overflows: true, moved: true });
    }

    await page.screenshot({ path: `test-results/advertising-${width}-list.png`, fullPage: true });
    await page.getByRole("tab", { name: "Несопоставленные контакты", exact: true }).click();
    await expect(page.locator(".ad-unassigned")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Кампания для сопоставления UTM", exact: true })
    ).toBeVisible();
    await page.getByRole("tab", { name: "Кампании", exact: true }).click();
    const dateTrigger = page.getByRole("button", { name: "Кампании созданы с (UTC)", exact: true });
    await dateTrigger.click();
    await expect(page.locator(".date-input-popover")).toBeVisible();
    await page.locator(".date-input-day:not([data-outside-month])").first().click();
    await page.keyboard.press("Escape");
    await page
      .getByRole("button", { name: "Очистить дату: Кампании созданы с (UTC)", exact: true })
      .click();
    await expect(dateTrigger).toBeFocused();
    await page.locator('[data-admin-action="create-ad"]').click();
    const createDialog = page.getByRole("dialog");
    await expect(createDialog.getByText("Данные кампании", { exact: true })).toBeVisible();
    await page.screenshot({ path: `test-results/advertising-${width}-create.png`, fullPage: true });
    const createWidth = await createDialog
      .locator(".admin-ad-dialog")
      .evaluate((el) => el.getBoundingClientRect().width);
    expect(createWidth).toBeLessThanOrEqual(width);
    if (width >= 1024) expect(createWidth).toBeGreaterThan(700);
    await createDialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await page.getByRole("button", { name: "Открыть кампанию", exact: true }).first().click();
    const workspace = page.locator(".ad-workspace");
    await expect(workspace).toBeVisible();
    for (const section of [
      "Обзор",
      "Ссылки",
      "Предложения",
      "Контакты и покупки",
      "Расходы",
      "Импорт CSV",
      "История изменений",
      "Настройки",
    ]) {
      await workspace.getByRole("tab", { name: section, exact: true }).click();
      await expect(workspace.getByRole("tab", { name: section, exact: true })).toHaveAttribute(
        "aria-selected",
        "true"
      );
      await expect(workspace.getByRole("alert")).toHaveCount(0);
      if (section === "Настройки") {
        const heights = await workspace
          .locator(".admin-form-grid .input, .admin-form-grid .admin-select-trigger")
          .evaluateAll((fields) =>
            fields.map((field) => Math.round(field.getBoundingClientRect().height))
          );
        expect(heights.length).toBeGreaterThan(4);
        expect(new Set(heights)).toEqual(new Set([40]));
      }
      if (section === "Импорт CSV") {
        await expect(
          workspace.getByRole("button", { name: "Выбрать файл: Файл CSV", exact: true })
        ).toBeVisible();
      }

      expect(
        await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
      ).toBe(false);
      await page.screenshot({
        path: `test-results/advertising-${width}-${section}.png`,
        fullPage: true,
      });
    }
    await workspace.getByRole("tab", { name: "Ссылки", exact: true }).click();
    await workspace.getByLabel("Название ссылки", { exact: true }).fill("QA generated link");
    await workspace.getByLabel("utm_source", { exact: true }).fill("telegram");
    await workspace.getByRole("button", { name: "Создать ссылку", exact: true }).click();
    await expect(workspace.getByText("QA generated link", { exact: true })).toBeVisible();
    await expect(workspace).toHaveAttribute("aria-busy", "false");
    expect(errors).toEqual([]);
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth + 1
    );
    expect(overflow).toBe(false);
  });
}

test("CSV preview can be confirmed and reverted without changing contacts", async ({ page }) => {
  await page.goto("/demo/runtime/admin/ads");
  await page.getByRole("button", { name: "Открыть кампанию", exact: true }).first().click();
  const workspace = page.locator(".ad-workspace");
  await workspace.getByRole("tab", { name: "Импорт CSV", exact: true }).click();
  await workspace.getByLabel("Рекламный аккаунт", { exact: true }).fill("QA CSV account");
  await workspace.getByLabel("Файл CSV", { exact: true }).setInputFiles({
    name: "advertising.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("date,ad,starts\n2026-09-01T00:00:00Z,qa,3\n"),
  });
  await expect(workspace.getByLabel("Содержимое CSV", { exact: true })).toHaveValue(
    "date,ad,starts\n2026-09-01T00:00:00Z,qa,3\n"
  );
  for (const [label, column] of [
    ["Начало интервала / время события", "date"],
    ["ID объявления", "ad"],
  ]) {
    await workspace.getByRole("button", { name: label, exact: true }).click();
    await page.getByRole("option", { name: column, exact: true }).click();
    await expect(page.getByRole("option")).toHaveCount(0);
  }
  await workspace.getByRole("button", { name: "Создать предпросмотр", exact: true }).click();
  await expect(workspace.getByRole("table", { name: "Предпросмотр: 1 строк" })).toBeVisible();
  await workspace.getByRole("button", { name: "Подтвердить весь импорт", exact: true }).click();
  await expect(workspace.getByText("QA CSV account", { exact: true })).toBeVisible();
  await workspace.getByRole("button", { name: "Отменить импорт", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Отменить импорт", exact: true })
    .click();
  await expect(workspace.getByRole("alert")).toHaveCount(0);
});
