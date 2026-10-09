import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const locales: Record<"ru" | "en", Record<string, string>> = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

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
    const saveRow = content.locator(".admin-tariff-settings-save-row");

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
    await expect(saveRow).toHaveCount(0);
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
    await input.fill("");
    await duration.fill(originalDuration);
    await save.click();
    await expect(saveRow).toHaveCount(0);
    await trigger.click();
    await expect(content).toHaveCount(0);
    await trigger.click();
    await expect(input).toHaveValue("");
    await expect(duration).toHaveValue(originalDuration);
    await page.screenshot({
      path: testInfo.outputPath(`trial-settings-${width}.png`),
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
}

for (const width of [1280, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`gift activation referral rule can be saved and reset at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((lang) => {
        localStorage.setItem("rw_minishop_demo_language", lang);
      }, language);
      await page.goto("/demo/runtime/admin/settings/referral?theme_preview=dark");

      const copy = locales[language];
      const content = page.locator("#admin-settings-section-referral");
      const trigger = page.locator('[aria-controls="admin-settings-section-referral"]');
      const giftRow = content.locator(".admin-setting").filter({
        has: page.getByText("REFERRAL_GIFT_ACTIVATION_ENABLED", { exact: true }),
      });
      const rules = giftRow.locator("xpath=..");
      const giftSwitch = giftRow.getByRole("switch", {
        name: copy.admin_tariffs_referral_gift_activation_enabled,
        exact: true,
      });
      const reset = giftRow.getByRole("button", { name: copy.admin_reset, exact: true });
      const saving = page.getByRole("button", { name: copy.admin_saving, exact: true });
      const save = page.getByRole("main").last().getByRole("button", {
        name: copy.admin_save,
        exact: true,
      });

      await expect(giftSwitch).toBeVisible();
      await expect(giftSwitch).toBeChecked();
      await expect(giftRow.locator("small")).toHaveText(
        copy.admin_tariffs_referral_gift_activation_enabled_hint
      );
      await expect(
        content.getByRole("switch", {
          name: copy.admin_tariffs_referral_one_bonus_per_referee,
          exact: true,
        })
      ).toBeVisible();

      await giftSwitch.click();
      await expect(giftSwitch).not.toBeChecked();
      await expect(save).toBeVisible();
      await reset.click();
      await expect(giftSwitch).toBeChecked();
      await expect(reset).toHaveCount(0);
      await expect(save).toHaveCount(0);

      await giftSwitch.focus();
      await page.keyboard.press("Space");
      await expect(giftSwitch).not.toBeChecked();
      await save.click();
      await expect(saving).toHaveCount(0);
      await expect(save).toHaveCount(0);
      await expect(content).toBeVisible();
      await trigger.click();
      await expect(content).toHaveCount(0);
      await trigger.click();
      await expect(giftSwitch).not.toBeChecked();
      await expect(reset).toHaveCount(0);

      await giftSwitch.click();
      await expect(giftSwitch).toBeChecked();
      await reset.click();
      await expect(giftSwitch).not.toBeChecked();
      await expect(save).toHaveCount(0);

      const bounds = await giftSwitch.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
      expect(
        await rules.evaluate((element) => element.scrollWidth - element.clientWidth)
      ).toBeLessThanOrEqual(2);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      await rules.screenshot({
        path: testInfo.outputPath(`gift-referral-${width}-${language}.png`),
      });

      await giftSwitch.click();
      await save.click();
      await expect(saving).toHaveCount(0);
      await expect(save).toHaveCount(0);
      await expect(content).toBeVisible();
      await trigger.click();
      await expect(content).toHaveCount(0);
      await trigger.click();
      await expect(giftSwitch).toBeChecked();
      expect(errors).toEqual([]);
    });
  }
}
