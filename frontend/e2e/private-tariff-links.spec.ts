import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";

const locales: Record<string, Record<string, string>> = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

for (const [width, language] of [
  [1440, "ru"],
  [390, "ru"],
  [768, "en"],
] as const) {
  test(`private tariff links share and rotate access at ${width}px in ${language}`, async ({
    page,
  }, testInfo) => {
    const t = locales[language];
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.addInitScript((lang) => {
      localStorage.setItem("rw_minishop_demo_language", lang);
    }, language);
    await page.goto(`/demo/runtime/admin/tariffs?theme_preview=dark&lang=${language}`);
    await page.locator('[data-admin-action="open-tariff-editor"]').first().click();
    const dialog = page.locator(".admin-tariff-dialog");
    const browser = dialog.getByRole("textbox", {
      name: t.admin_tariff_checkout_link_browser,
      exact: true,
    });
    const miniapp = dialog.getByRole("textbox", {
      name: t.admin_tariff_checkout_link_miniapp,
      exact: true,
    });
    await expect(browser).toHaveValue(/\/checkout\?plan=standard$/);
    await expect(miniapp).toHaveValue("https://t.me/preview_bot?startapp=plan_standard");
    await dialog.getByRole("switch", { name: t.admin_tariff_enabled, exact: true }).click();
    await expect(miniapp).toHaveValue(t.admin_tariff_checkout_link_unavailable);
    await dialog
      .getByRole("switch", { name: t.admin_tariff_link_access_title, exact: true })
      .click();
    await expect(browser).toHaveValue(/\/checkout\/[a-f0-9]{32}$/);
    const code = (await browser.inputValue()).split("/").pop()!;
    await expect(miniapp).toHaveValue(`https://t.me/preview_bot?startapp=checkout_${code}`);
    expect((await browser.boundingBox())!.width).toBeGreaterThan(140);
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    for (const field of await dialog.locator(".copy-link-field").all()) {
      await field
        .getByRole("button", { name: t.admin_tariff_checkout_link_copy, exact: true })
        .click();
      const value = await field.getByRole("textbox").inputValue();
      await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(value);
    }
    await miniapp.click();
    expect(
      await miniapp.evaluate(
        (input: HTMLInputElement) => input.selectionEnd! - input.selectionStart!
      )
    ).toBe((await miniapp.inputValue()).length);
    await expect(dialog.locator(".copy-link-field")).toHaveCount(2);
    const overflow = await dialog.evaluate((element) => element.scrollWidth - element.clientWidth);
    expect(overflow).toBeLessThanOrEqual(2);
    await browser.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`private-links-${width}.png`) });
    await dialog
      .getByRole("button", { name: t.admin_tariff_link_access_regenerate, exact: true })
      .click();
    await expect(browser).not.toHaveValue(new RegExp(`${code}$`));
    const rotated = (await browser.inputValue()).split("/").pop()!;
    await expect(miniapp).toHaveValue(`https://t.me/preview_bot?startapp=checkout_${rotated}`);
    await dialog
      .getByRole("switch", { name: t.admin_tariff_link_access_title, exact: true })
      .click();
    await expect(browser).toHaveValue(t.admin_tariff_checkout_link_unavailable);
    await expect(miniapp).toHaveValue(t.admin_tariff_checkout_link_unavailable);
    for (const button of await dialog
      .locator(".copy-link-field")
      .getByRole("button", { name: t.admin_tariff_checkout_link_copy, exact: true })
      .all()) {
      await expect(button).toBeDisabled();
    }
    expect(errors).toEqual([]);
  });
}
