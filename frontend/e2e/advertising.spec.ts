import { expect, test } from "@playwright/test";

for (const width of [1440, 390]) {
  test(`advertising campaign sections work at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto("/demo/runtime/admin/ads");
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
      await workspace.getByRole("button", { name: section, exact: true }).click();
      await expect(workspace.getByRole("button", { name: section, exact: true })).toHaveAttribute(
        "aria-pressed",
        "true"
      );
      await expect(workspace.getByRole("alert")).toHaveCount(0);
    }
    await workspace.getByRole("button", { name: "Ссылки", exact: true }).click();
    await workspace.getByLabel("Название ссылки", { exact: true }).fill("QA generated link");
    await workspace.getByLabel("utm_source", { exact: true }).fill("telegram");
    await workspace.getByRole("button", { name: "Создать ссылку", exact: true }).click();
    await expect(workspace.getByRole("heading", { name: "QA generated link" })).toBeVisible();
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
  await workspace.getByRole("button", { name: "Импорт CSV", exact: true }).click();
  await workspace.getByLabel("Рекламный аккаунт", { exact: true }).fill("QA CSV account");
  await workspace
    .getByLabel("Содержимое CSV", { exact: true })
    .fill("date,ad,starts\n2026-09-01T00:00:00Z,qa,3\n");
  for (const [label, column] of [
    ["Начало интервала / время события", "date"],
    ["ID объявления", "ad"],
  ]) {
    await workspace.getByRole("button", { name: label, exact: true }).click();
    await page.getByRole("option", { name: column, exact: true }).click();
    await expect(page.getByRole("option")).toHaveCount(0);
  }
  await workspace.getByRole("button", { name: "Создать предпросмотр", exact: true }).click();
  await expect(workspace.getByRole("heading", { name: "Предпросмотр: 1 строк" })).toBeVisible();
  await workspace.getByRole("button", { name: "Подтвердить весь импорт", exact: true }).click();
  await expect(workspace.getByText("QA CSV account", { exact: true })).toBeVisible();
  await workspace.getByRole("button", { name: "Отменить импорт", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Отменить импорт", exact: true })
    .click();
  await expect(workspace.getByRole("alert")).toHaveCount(0);
});
