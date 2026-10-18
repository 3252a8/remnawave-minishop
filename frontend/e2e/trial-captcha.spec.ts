import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

const reviewDirectory = resolve("../../review-133-ui");
mkdirSync(reviewDirectory, { recursive: true });
const reviewPath = (name: string) => join(reviewDirectory, name);

const locales: Record<"ru" | "en", Record<string, string>> = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

for (const width of [1440, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`settings search opens and saves trial CAPTCHA at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const copy = locales[language];
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((lang) => {
        localStorage.setItem("rw_minishop_demo_language", lang);
      }, language);
      await page.goto("/demo/runtime/admin/settings?theme_preview=dark");
      const search = page.getByRole("searchbox", { name: copy.admin_settings_search_aria });
      await search.fill(language === "ru" ? "капча" : "captcha");
      const result = page.getByRole("option").filter({
        has: page.getByText("TRIAL_CAPTCHA_ENABLED", { exact: true }),
      });
      await expect(result).toHaveCount(1);
      await page.locator("#admin-settings-search-results").screenshot({
        path: testInfo.outputPath(`captcha-search-${width}-${language}.png`),
      });
      await result.click();
      await expect(page).toHaveURL(/\/admin\/tariffs.*#settings-field:TRIAL_CAPTCHA_ENABLED$/);
      const content = page.locator("#admin-trial-settings-content");
      const row = content.locator(".admin-setting").filter({
        has: page.getByText("TRIAL_CAPTCHA_ENABLED", { exact: true }),
      });
      await expect(row).toBeInViewport();
      await expect(row).toBeFocused();
      await row.screenshot({
        path: testInfo.outputPath(`captcha-target-${width}-${language}.png`),
      });
      const control = row.getByRole("switch", { name: copy.admin_settings_trial_captcha_label });
      await expect(control).not.toBeChecked();
      await control.click();
      await content.getByRole("button", { name: copy.admin_save, exact: true }).click();
      await expect(content.locator(".admin-tariff-settings-save-row")).toHaveCount(0);
      await expect(control).toBeChecked();
      await control.click();
      await content.getByRole("button", { name: copy.admin_save, exact: true }).click();
      await expect(content.locator(".admin-tariff-settings-save-row")).toHaveCount(0);
      await expect(control).not.toBeChecked();
      expect(errors).toEqual([]);
    });
  }

  test(`trial CAPTCHA defaults off and can be saved or reset at ${width}px`, async ({
    page,
  }, testInfo) => {
    const copy = locales.ru;
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/tariffs?theme_preview=dark");
    const trigger = page.getByRole("button", { name: /^Пробный период/ });
    await trigger.click();
    const content = page.locator("#admin-trial-settings-content");
    const row = content.locator(".admin-trial-setting-row").filter({
      has: page.getByText("TRIAL_CAPTCHA_ENABLED", { exact: true }),
    });
    const control = row.getByRole("switch", { name: copy.admin_settings_trial_captcha_label });
    const save = content.getByRole("button", { name: copy.admin_save, exact: true });
    await expect(control).not.toBeChecked();
    await row.scrollIntoViewIfNeeded();
    await row.screenshot({ path: testInfo.outputPath(`captcha-setting-${width}.png`) });
    await control.click();
    await expect(control).toBeChecked();
    await row.getByRole("button", { name: copy.admin_reset, exact: true }).click();
    await expect(control).not.toBeChecked();
    await control.click();
    await save.click();
    await expect(content.locator(".admin-tariff-settings-save-row")).toHaveCount(0);
    await trigger.click();
    await trigger.click();
    await expect(control).toBeChecked();
    await control.click();
    await save.click();
    await expect(content.locator(".admin-tariff-settings-save-row")).toHaveCount(0);
    await expect(control).not.toBeChecked();
  });

  test(`account cleanup starts disabled with 30-day rules at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/settings/system?theme_preview=dark");
    const card = page.locator(".admin-settings-subsection").filter({
      has: page.locator('[data-settings-anchor="settings-subsection:system:account_cleanup"]'),
    });
    const trigger = card.locator(".admin-settings-subsection-trigger");
    if ((await trigger.getAttribute("data-state")) === "closed") await trigger.click();
    const switches = card.getByRole("switch");
    await expect(switches).toHaveCount(3);
    for (const control of await switches.all()) await expect(control).not.toBeChecked();
    for (const key of ["UNUSED_ACCOUNTS_NO_TRIAL_DAYS", "UNUSED_ACCOUNTS_UNUSED_TRIAL_DAYS"]) {
      const row = card.locator(".admin-setting").filter({
        has: page.getByText(key, { exact: true }),
      });
      await expect(row.locator("input")).toHaveValue("30");
    }
  });
}

for (const width of [320, 390, 768, 1440]) {
  for (const language of ["ru", "en"] as const) {
    for (const mode of ["dark", "light"] as const) {
      test(`trial verification stays usable at ${width}px in ${language} ${mode}`, async ({
        page,
      }) => {
        const copy = locales[language];
        const errors: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.setViewportSize({ width, height: 800 });
        await page.addInitScript(
          ({ language, mode }) => {
            localStorage.setItem("rw_minishop_demo_language", language);
            localStorage.setItem("rw_webapp_theme_mode_v1", mode);
          },
          { language, mode }
        );
        await page.goto(`/demo/runtime/app/?mock=trial-captcha&theme_preview=${mode}`);
        const activate = page.getByRole("button", { name: copy.wa_trial_try_free, exact: true });
        await activate.click();
        const dialog = page.getByRole("dialog", { name: copy.wa_trial_captcha_title });
        const card = dialog.locator(".trial-captcha-dialog");
        const answer = dialog.getByLabel(copy.wa_trial_captcha_answer_label);
        const refresh = dialog.getByRole("button", { name: copy.wa_trial_captcha_refresh });
        const close = dialog.locator(".dialog-close-button");
        const submit = dialog.getByRole("button", {
          name: copy.wa_trial_captcha_continue,
          exact: true,
        });
        await expect(dialog.getByRole("img")).toBeVisible();
        await expect(page.locator(".app-shell")).toHaveClass(new RegExp(`\\btheme-${mode}\\b`));
        await expect(dialog.locator("input")).toHaveCount(1);
        await expect(answer).toHaveAttribute("inputmode", "numeric");
        await expect(answer).toBeFocused();
        await expect(submit).toBeDisabled();
        const dimensions = await card.boundingBox();
        expect(dimensions!.width).toBeLessThanOrEqual(Math.min(420, width - 28));
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
          width
        );
        expect(await answer.evaluate((node) => getComputedStyle(node).textAlign)).toBe("center");
        const gradients = await dialog.evaluate((element) =>
          [element, ...element.querySelectorAll("*")].flatMap((node) =>
            [null, "::before", "::after"].flatMap((pseudo) => {
              const background = getComputedStyle(node, pseudo).backgroundImage;
              return background.includes("gradient") ? [background] : [];
            })
          )
        );
        expect(gradients).toEqual([]);
        await answer.fill("73146");
        const focusedCode = await answer.evaluate((node) => {
          const style = getComputedStyle(node);
          const input = node.getBoundingClientRect();
          const viewport = node.closest(".scroll-area__viewport")!.getBoundingClientRect();
          return {
            outline: style.outlineStyle,
            shadow: style.boxShadow,
            border: parseFloat(style.borderTopWidth),
            tracking: parseFloat(style.letterSpacing),
            compensation: parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
            font: style.fontFamily,
            leftGap: input.left - viewport.left,
            rightGap: viewport.right - input.right,
          };
        });
        expect(focusedCode.outline).toBe("none");
        expect(focusedCode.shadow).toBe("none");
        expect(focusedCode.border).toBe(2);
        expect(focusedCode.font).toMatch(/mono|consolas/i);
        expect(focusedCode.tracking).toBeLessThan(5);
        expect(Math.abs(focusedCode.compensation - focusedCode.tracking)).toBeLessThan(0.1);
        expect(focusedCode.leftGap).toBeGreaterThanOrEqual(0);
        expect(focusedCode.rightGap).toBeGreaterThanOrEqual(0);
        await page.screenshot({
          path: reviewPath(`v3-${width}-${language}-${mode}-filled.png`),
          animations: "disabled",
          caret: "initial",
        });
        if (language === "ru" && (width === 1440 || width === 390)) {
          const device = width === 1440 ? "desktop" : "mobile";
          await page.screenshot({
            path: reviewPath(`v3-${device}-${mode}-filled.png`),
            animations: "disabled",
            caret: "initial",
          });
          if (width === 1440) {
            const bounds = (await card.boundingBox())!;
            await page.screenshot({
              path: reviewPath(`v3-desktop-${mode}-filled-detail.png`),
              animations: "disabled",
              caret: "initial",
              clip: {
                x: bounds.x - 32,
                y: bounds.y - 32,
                width: bounds.width + 64,
                height: bounds.height + 64,
              },
            });
          }
        }
        await answer.press("ControlOrMeta+A");
        expect(
          await answer.evaluate((node: HTMLInputElement) => [
            node.selectionStart,
            node.selectionEnd,
          ])
        ).toEqual([0, 5]);
        await page.screenshot({
          path: reviewPath(`v3-${width}-${language}-${mode}-selected.png`),
          animations: "disabled",
          caret: "initial",
        });
        if (language === "ru" && (width === 1440 || width === 390))
          await page.screenshot({
            path: reviewPath(`v3-${width === 1440 ? "desktop" : "mobile"}-${mode}-selected.png`),
            animations: "disabled",
            caret: "initial",
          });
        await answer.press("ArrowRight");
        await page.keyboard.press("Tab");
        await expect(submit).toBeFocused();
        expect(
          await submit.evaluate((node) => parseFloat(getComputedStyle(node).outlineOffset))
        ).toBeLessThan(0);
        await page.keyboard.press("Shift+Tab");
        await expect(answer).toBeFocused();
        await answer.fill("");
        await page.keyboard.press("Shift+Tab");
        await expect(refresh).toBeFocused();
        expect(
          await refresh.evaluate((node) => parseFloat(getComputedStyle(node).outlineOffset))
        ).toBeLessThan(0);
        await page.keyboard.press("Shift+Tab");
        await expect(close).toBeFocused();
        await page.keyboard.press("Shift+Tab");
        await expect(answer).toBeFocused();
        await page.keyboard.press("Escape");
        await expect(dialog).not.toBeVisible();
        await expect(activate).toBeEnabled();
        await activate.click();
        await expect(answer).toBeFocused();
        await answer.fill("00000");
        await answer.press("Enter");
        await expect(dialog.getByRole("alert")).toHaveText(copy.wa_trial_captcha_invalid);
        await expect(answer).toBeFocused();
        if (width === 390)
          await page.screenshot({
            path: reviewPath(`v3-error-${width}-${language}-${mode}.png`),
            animations: "disabled",
            caret: "initial",
          });
        await page.keyboard.press("Shift+Tab");
        await page.keyboard.press("Space");
        await expect(answer).toHaveValue("");
        await expect(dialog.getByRole("alert")).toHaveCount(0);
        await expect(answer).toBeFocused();
        await answer.fill("73146");
        await submit.hover();
        expect(await submit.evaluate((node) => getComputedStyle(node).backgroundImage)).toBe(
          "none"
        );
        await answer.press("Enter");
        await expect(dialog).not.toBeVisible();
        await expect(page.getByText(copy.wa_trial_activated, { exact: true })).toBeVisible();
        expect(errors).toEqual([]);
      });
    }
  }
}

for (const width of [320, 390]) {
  for (const language of ["ru", "en"] as const) {
    for (const mode of ["dark", "light"] as const) {
      test(`trial verification scrolls above a keyboard at ${width}px in ${language} ${mode}`, async ({
        page,
      }) => {
        const copy = locales[language];
        await page.setViewportSize({ width, height: 480 });
        await page.addInitScript(
          ({ language, mode }) => {
            localStorage.setItem("rw_minishop_demo_language", language);
            localStorage.setItem("rw_webapp_theme_mode_v1", mode);
          },
          { language, mode }
        );
        await page.goto(`/demo/runtime/app/?mock=trial-captcha&theme_preview=${mode}`);
        await page.getByRole("button", { name: copy.wa_trial_try_free, exact: true }).click();
        const dialog = page.getByRole("dialog", { name: copy.wa_trial_captcha_title });
        const answer = dialog.getByLabel(copy.wa_trial_captcha_answer_label);
        await expect(page.locator(".app-shell")).toHaveClass(new RegExp(`\\btheme-${mode}\\b`));
        await expect(answer).toBeFocused();
        await answer.fill("73146");
        const image = dialog.getByRole("img");
        const initialSubmit = dialog.getByRole("button", {
          name: copy.wa_trial_captcha_continue,
          exact: true,
        });
        await expect(image).toBeInViewport({ ratio: 1 });
        await expect(answer).toBeInViewport({ ratio: 1 });
        await expect(initialSubmit).toBeInViewport({ ratio: 1 });
        await page.screenshot({
          path: reviewPath(`v3-short-initial-${width}-${language}-${mode}-filled.png`),
          animations: "disabled",
          caret: "initial",
        });
        await answer.fill("00000");
        await answer.press("Enter");
        await expect(dialog.getByRole("alert")).toBeVisible();
        const submit = dialog.getByRole("button", {
          name: copy.wa_trial_captcha_continue,
          exact: true,
        });
        await submit.scrollIntoViewIfNeeded();
        await expect(submit).toBeInViewport();
        const hint = dialog.locator("#trial-captcha-hint");
        await hint.scrollIntoViewIfNeeded();
        await expect(hint).toBeInViewport();
        expect(
          (await dialog.locator(".trial-captcha-dialog").boundingBox())!.height
        ).toBeLessThanOrEqual(452);
        await page.screenshot({
          path: reviewPath(`v3-short-${width}-${language}-${mode}-error.png`),
          animations: "disabled",
          caret: "initial",
        });
        await answer.fill("73146");
        await answer.press("Enter");
        await expect(dialog).not.toBeVisible();
      });
    }
  }
}
