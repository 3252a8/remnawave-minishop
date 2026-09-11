import { test, expect } from "@playwright/test";
import path from "node:path";
import { readFileSync } from "node:fs";
import { strToU8, zipSync, unzipSync } from "fflate";

const url = "/demo/runtime/app/?screen=admin&admin_section=appearance";
const sample = path.resolve("../docs-site/public/demo/theme-examples.zip");

for (const viewport of [
  { width: 1280, height: 900 },
  { width: 390, height: 844 },
]) {
  test("theme library lifecycle " + viewport.width, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(url);
    const library = page.locator(".appearance-library");
    await expect(library).toBeVisible();
    const actionBar = library.locator(".appearance-action-bar");
    await expect(actionBar.getByRole("button")).toHaveCount(5);
    expect(
      new Set(
        await actionBar
          .getByRole("button")
          .evaluateAll((buttons) =>
            buttons.map((button) => Math.round(button.getBoundingClientRect().top))
          )
      ).size
    ).toBe(1);
    await expect(library).not.toContainText("Новые темы добавляются в библиотеку");
    await expect(library).not.toContainText("Ваш магазин, ваш стиль");
    await expect(library).not.toContainText("Выберите тему, добавьте свою");
    await expect(library.locator(".library-theme-card")).toHaveCount(3);
    expect(
      await library.locator(".library-theme-card").evaluateAll((cards) =>
        cards.every((card) => {
          const actions = card.querySelector(".theme-card-actions");
          return (
            actions &&
            card.getBoundingClientRect().bottom - actions.getBoundingClientRect().bottom <= 20
          );
        })
      )
    ).toBe(true);
    await expect
      .poll(async () =>
        library
          .locator(".theme-screenshot img")
          .evaluateAll((images) =>
            images.every(
              (image) =>
                image instanceof HTMLImageElement && image.complete && image.naturalWidth > 0
            )
          )
      )
      .toBe(true);
    await expect(page.locator(".default-theme-editor")).toBeHidden();
    await library.locator('[data-theme-key="dark"] .theme-card-actions button').last().click();
    const defaultSettings = page.locator(".appearance-settings-dialog");
    await expect(defaultSettings.locator(".default-theme-editor")).toBeVisible();
    await defaultSettings.locator(".dialog-head button").click();
    await expect(defaultSettings).toBeHidden();

    await library.getByRole("button", { name: "Добавить темы", exact: true }).click();
    let dialog = page.locator(".appearance-import-dialog");
    await expect(dialog).toBeVisible();
    await dialog.locator('input[type="file"]').setInputFiles(sample);
    await expect(dialog.locator(".import-candidate")).toHaveCount(2);
    await dialog.getByRole("button", { name: /Установить/ }).click();
    await expect(dialog).toBeHidden();
    await expect(library.locator(".library-theme-card")).toHaveCount(5);
    await expect(library.locator('[data-theme-key="dark"]')).toHaveClass(/active/);

    const ocean = library.locator('[data-theme-key="ocean"]');
    const popupPromise = page.waitForEvent("popup");
    await ocean.locator(".theme-card-actions button").first().click();
    const preview = await popupPromise;
    await preview.waitForLoadState();
    await expect(preview).toHaveURL(/\/demo\/runtime\/app\/\?theme_preview=ocean$/);
    await expect(preview.locator(".app-shell")).toHaveClass(/theme-key-ocean/);
    await expect(page.locator(".appearance-preview-dialog")).toHaveCount(0);
    await preview.close();

    await ocean.getByRole("button", { name: "Активировать", exact: true }).click();
    await expect(ocean).toHaveClass(/active/);
    await ocean.locator(".theme-card-actions button").last().click();
    let settings = page.locator(".appearance-settings-dialog");
    await expect(
      settings.getByRole("button", { name: "Удалить тему", exact: true })
    ).toBeDisabled();
    await settings.locator(".dialog-head button").click();
    await library
      .locator('[data-theme-key="dark"]')
      .getByRole("button", { name: "Активировать", exact: true })
      .click();

    await library.getByRole("button", { name: "Добавить темы", exact: true }).click();
    dialog = page.locator(".appearance-import-dialog");
    await dialog.locator('input[type="file"]').setInputFiles(sample);
    await expect(dialog.getByRole("button", { name: /Установить/ })).toBeDisabled();
    const update = unzipSync(readFileSync(sample));
    update["ocean/theme-package.json"] = strToU8(
      JSON.stringify({ schema_version: 1, version: "2.0.0", compatibility: { theme_api: 1 } })
    );
    await dialog.getByRole("button", { name: "Назад", exact: true }).click();
    await dialog.locator('input[type="file"]').setInputFiles({
      name: "update.zip",
      mimeType: "application/zip",
      buffer: Buffer.from(zipSync(update)),
    });
    await dialog.getByRole("button", { name: "Если тема уже установлена", exact: true }).click();
    await page.getByRole("option", { name: /Обновить/ }).click();
    await dialog.getByRole("button", { name: /Установить/ }).click();
    await expect(dialog).toBeHidden();
    await ocean.locator(".theme-card-actions button").last().click();
    settings = page.locator(".appearance-settings-dialog");
    await settings.getByRole("button", { name: "Вернуть предыдущую версию", exact: true }).click();
    await expect(settings).toBeHidden();

    await ocean.locator(".theme-card-actions button").last().click();
    await settings.getByRole("button", { name: "Скачать", exact: true }).click();
    const exportDialog = page
      .locator(".dialog-card")
      .filter({ has: page.getByRole("button", { name: "Скачать ZIP", exact: true }) });
    await exportDialog.getByRole("textbox").fill("my-ocean");
    const downloadPromise = page.waitForEvent("download");
    await exportDialog.getByRole("button", { name: "Скачать ZIP", exact: true }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe("my-ocean.zip");
    await expect(settings).toBeHidden();
    await ocean.locator(".theme-card-actions button").last().click();
    await settings.getByRole("button", { name: "Удалить тему", exact: true }).click();
    const removeDialog = page
      .locator(".dialog-card")
      .filter({ has: page.getByRole("heading", { name: "Удалить тему", exact: true }) });
    await removeDialog.getByRole("button", { name: "Удалить тему", exact: true }).click();
    await expect(ocean).toHaveCount(0);
    expect(
      await library.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)
    ).toBe(true);
    expect(errors).toEqual([]);
  });
}

test("theme import rejects unsafe archives and protected keys", async ({ page }) => {
  await page.goto(url);
  await page
    .locator(".appearance-library")
    .getByRole("button", { name: "Добавить темы", exact: true })
    .click();
  const dialog = page.locator(".appearance-import-dialog");
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "bad.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(zipSync({ "../escape/theme.json": strToU8("{}") })),
  });
  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(dialog.getByRole("button", { name: /Установить/ })).toHaveCount(0);
  await dialog.locator('input[type="file"]').setInputFiles({
    name: "protected.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(zipSync({ "dark/theme.json": strToU8(JSON.stringify({ key: "dark" })) })),
  });
  await expect(dialog.locator(".import-candidate")).toHaveCount(1);
  await expect(dialog.getByRole("button", { name: /Установить/ })).toBeDisabled();
});

for (const layout of [
  { name: "wide", width: 1600, addCardFillsRow: false },
  { name: "desktop", width: 1280, addCardFillsRow: true },
  { name: "mobile", width: 390, addCardFillsRow: true },
]) {
  test(`theme grid cards have equal heights on ${layout.name}`, async ({ page }) => {
    await page.setViewportSize({ width: layout.width, height: 900 });
    await page.goto(url);
    const library = page.locator(".appearance-library");
    await expect(library.locator(".library-theme-card")).toHaveCount(3);
    const metrics = await library.locator(".theme-library-grid").evaluate((grid) => {
      const themes = [...grid.querySelectorAll(".library-theme-card")];
      const addCard = grid.querySelector(".theme-add-card");
      return {
        gridWidth: grid.getBoundingClientRect().width,
        themeWidth: themes[0]?.getBoundingClientRect().width || 0,
        addCardWidth: addCard?.getBoundingClientRect().width || 0,
        heights: [...themes, addCard]
          .filter((card): card is Element => Boolean(card))
          .map((card) => card.getBoundingClientRect().height),
      };
    });
    expect(Math.max(...metrics.heights) - Math.min(...metrics.heights)).toBeLessThanOrEqual(1);
    expect(metrics.addCardWidth).toBeCloseTo(
      layout.addCardFillsRow ? metrics.gridWidth : metrics.themeWidth,
      0
    );
  });
}

test("theme library supports repository review, Escape and archive drop", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(url);
  const library = page.locator(".appearance-library");
  await library.getByRole("button", { name: "Добавить темы", exact: true }).click();
  const dialog = page.locator(".appearance-import-dialog");
  await dialog.getByRole("button", { name: "Git-репозиторий", exact: true }).click();
  await dialog.locator('input[type="url"]').fill("https://gitlab.com/author/group/themes");
  await dialog.getByRole("button", { name: "Найти темы", exact: true }).click();
  await expect(dialog.locator(".import-candidate")).toHaveCount(2);
  await expect(dialog.locator(":focus")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await library.getByRole("button", { name: "Добавить темы", exact: true }).click();
  const transfer = await page.evaluateHandle(
    (bytes) => {
      const data = new DataTransfer();
      data.items.add(new File([new Uint8Array(bytes)], "dropped.zip", { type: "application/zip" }));
      return data;
    },
    Array.from(readFileSync(sample))
  );
  await dialog.locator(".import-drop").dispatchEvent("drop", { dataTransfer: transfer });
  await expect(dialog.locator(".import-candidate")).toHaveCount(2);
  await expect(dialog.getByRole("button", { name: /Установить/ })).toBeEnabled();
  await expect(dialog.locator(":focus")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
});

for (const width of [1280, 390]) {
  test("legacy theme without metadata remains usable " + width, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors: string[] = [];
    const thumbnails: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(message.text());
    });
    page.on("request", (request) => {
      if (request.url().includes("CustomTheme/preview")) thumbnails.push(request.url());
    });
    await page.route("**/themes/ascii/preview.webp*", (route) =>
      route.fulfill({
        status: 200,
        contentType: "image/webp",
        body: "broken image",
      })
    );
    await page.goto(url + "&mock=legacy-themes");
    const library = page.locator(".appearance-library");
    const theme = library.locator('[data-theme-key="CustomTheme"]');
    await expect(theme).toBeVisible();
    await expect(theme).toHaveClass(/active/);
    await expect(theme.locator(".theme-screenshot img")).toHaveCount(0);
    await expect(theme.locator(".theme-screenshot")).toContainText("Автор не добавил скриншот");
    const popupPromise = page.waitForEvent("popup");
    await theme.locator(".theme-card-actions button").first().click();
    const preview = await popupPromise;
    await preview.waitForLoadState();
    await expect(preview).toHaveURL(/theme_preview=CustomTheme/);
    await expect(preview.locator(".app-shell")).toHaveClass(/theme-key-customtheme/);
    await expect(page.locator(".appearance-preview-dialog")).toHaveCount(0);
    await preview.close();
    await library
      .locator('[data-theme-key="dark"]')
      .getByRole("button", { name: "Активировать", exact: true })
      .click();
    await theme.getByRole("button", { name: "Активировать", exact: true }).click();
    await expect(theme).toHaveClass(/active/);
    await theme.locator(".theme-card-actions button").last().click();
    const settings = page.locator(".appearance-settings-dialog");
    await expect(settings).toBeVisible();
    const accent = settings
      .locator(".appearance-token-control")
      .filter({ hasText: "Акцент" })
      .locator("input.appearance-color-text");
    await accent.fill("#aabbcc");
    await settings.locator(".dialog-head button").click();
    await expect(settings).toBeHidden();
    const save = library.getByRole("button", { name: "Сохранить", exact: true });
    await save.click();
    await expect(save).toBeDisabled();
    await theme.locator(".theme-card-actions button").last().click();
    await expect(accent).toHaveValue("#aabbcc");
    await settings.locator(".dialog-head button").click();
    expect(
      await library.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)
    ).toBe(true);
    await expect(library.locator('[data-theme-key="ascii"] .theme-screenshot')).toContainText(
      "Автор не добавил скриншот"
    );
    expect(thumbnails).toEqual([]);
    expect(errors).toEqual([]);
  });
}
