import { expect, test, type Locator } from "@playwright/test";

async function expectAnimationSetting(flows: Locator, animated: boolean): Promise<void> {
  await expect(flows.first()).toBeVisible();
  await expect
    .poll(() =>
      flows.evaluateAll(
        (nodes, enabled) =>
          nodes.every((node) => (node as HTMLElement & { animated: boolean }).animated === enabled),
        animated
      )
    )
    .toBe(true);
  if (!animated) {
    expect(
      await flows.evaluateAll(
        (nodes) =>
          nodes
            .flatMap((node) => node.shadowRoot?.getAnimations() || [])
            .filter((animation) => animation.playState === "running").length
      )
    ).toBe(0);
  }
}

for (const width of [390, 1280]) {
  for (const [flow, mock] of [
    ["purchase", "no-subscription"],
    ["renewal", "checkout-addons"],
  ]) {
    test(`${flow} prices follow the animation setting at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(() => {
        const key = "minishop-demo-settings-changes";
        if (sessionStorage.getItem(key)) return;
        sessionStorage.setItem(
          key,
          JSON.stringify([
            ["WEBAPP_CHECKOUT_ADDON_VALUE_ANIMATION_ENABLED", { value: false, deleted: false }],
          ])
        );
      });
      await page.goto(`/demo/runtime/home?mock=${mock}&theme_preview=dark`);

      for (const animated of [false, true]) {
        await page.locator('[data-webapp-action="open-payment"]:visible').first().click();
        const dialog = page.locator(".dialog-card.webapp-payment-dialog");
        await expect(dialog).toBeVisible();
        const tariffs = dialog.locator(".tariff-row");
        if (await tariffs.count()) {
          await tariffs.first().click();
          await dialog.locator(".payment-submit-button").first().click();
        }

        const periodPrices = dialog.locator(".period-card number-flow-svelte.animated-price");
        const unitPrices = dialog.locator(".period-unit-price number-flow-svelte");
        const paymentPrices = dialog.locator(".payment-submit-button number-flow-svelte");
        await expectAnimationSetting(periodPrices, animated);
        await expectAnimationSetting(unitPrices, animated);
        await expectAnimationSetting(paymentPrices, animated);

        const previousPrice = await paymentPrices.first().getAttribute("aria-label");
        await dialog.locator(".period-card").last().click();
        await expect(paymentPrices.first()).not.toHaveAttribute("aria-label", previousPrice!);
        await expectAnimationSetting(periodPrices, animated);
        await expectAnimationSetting(paymentPrices, animated);

        const promoInput = dialog.locator(".checkout-promo-input");
        await promoInput.fill("SAVE20");
        await dialog.locator(".checkout-promo-action .btn").click();
        await expect(promoInput).toHaveAttribute("readonly", "");
        await expect(dialog.locator(".period-card .promo-price-pair").first()).toBeVisible();
        await expect(dialog.locator(".payment-submit-button .promo-price-pair")).toBeVisible();
        await expectAnimationSetting(periodPrices, animated);
        await expectAnimationSetting(unitPrices, animated);
        await expectAnimationSetting(paymentPrices, animated);

        if (flow === "renewal") {
          await dialog.locator(".checkout-tariff-summary-button").click();
          const slider = dialog.getByRole("slider").first();
          const priceBeforeAddon = await paymentPrices.last().getAttribute("aria-label");
          await slider.press("End");
          await expect(paymentPrices.last()).not.toHaveAttribute("aria-label", priceBeforeAddon!);
          await expectAnimationSetting(dialog.locator("number-flow-svelte"), animated);
        }

        if (!animated) {
          await page.evaluate(() => {
            sessionStorage.setItem(
              "minishop-demo-settings-changes",
              JSON.stringify([
                ["WEBAPP_CHECKOUT_ADDON_VALUE_ANIMATION_ENABLED", { value: true, deleted: false }],
              ])
            );
          });
          await page.reload();
        }
      }
      expect(errors).toEqual([]);
    });
  }
}
