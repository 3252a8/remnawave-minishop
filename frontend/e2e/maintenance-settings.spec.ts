import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const locales: Record<"ru" | "en", Record<string, string>> = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

for (const width of [1280, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`automatic maintenance controls save without changing manual mode at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((lang) => {
        localStorage.setItem("rw_minishop_demo_language", lang);
      }, language);
      await page.goto("/demo/runtime/admin/settings/general?theme_preview=dark");
      const copy = locales[language];
      const manual = page.locator(
        '[data-settings-anchor="settings-field:MAINTENANCE_MODE_ENABLED"]'
      );
      const automatic = page.locator(
        '[data-settings-anchor="settings-field:MAINTENANCE_MODE_AUTO_ENABLED"]'
      );
      const delay = page.locator(
        '[data-settings-anchor="settings-field:MAINTENANCE_MODE_AUTO_DELAY_SECONDS"]'
      );
      const manualToggle = manual.getByRole("switch").or(manual.getByRole("checkbox"));
      const automaticToggle = automatic.getByRole("switch").or(automatic.getByRole("checkbox"));
      const originalManual = await manualToggle.getAttribute("aria-checked");
      await expect(automaticToggle).toHaveAccessibleName(
        copy.admin_settings_field_maintenance_mode_auto_enabled_label
      );
      await expect(automaticToggle).toHaveAttribute("aria-checked", "false");
      await automaticToggle.click();
      await expect(automaticToggle).toHaveAttribute("aria-checked", "true");
      const duration = delay.getByRole("spinbutton");
      await expect(duration).toHaveAccessibleName(
        copy.admin_settings_field_maintenance_mode_auto_delay_seconds_label
      );
      await duration.fill("120");
      const save = page
        .locator("header")
        .getByRole("button", { name: copy.admin_save, exact: true });
      await save.click();
      const saving = page
        .locator("header")
        .getByRole("button", { name: copy.admin_saving, exact: true });
      await expect(saving).toHaveCount(0);
      await expect(save).toBeDisabled();
      await expect(automaticToggle).toHaveAttribute("aria-checked", "true");
      await expect(duration).toHaveValue("120");
      expect(await manualToggle.getAttribute("aria-checked")).toBe(originalManual);
      await automatic.scrollIntoViewIfNeeded();
      await delay.scrollIntoViewIfNeeded();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      await page.screenshot({
        path: testInfo.outputPath(`automatic-maintenance-${width}-${language}.png`),
      });
    });
  }
}
