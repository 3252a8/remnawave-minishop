import path from "node:path";
import { expect, test } from "@playwright/test";

const screenshots = path.resolve("../.tmp/issue62");
const checkout =
  "/demo/runtime/app/?path=/checkout&plan=standard&months=1&mock=balance-recurring&theme_preview=dark";

for (const [device, viewport] of [
  ["desktop", { width: 1400, height: 1000 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`balance provider links and recurring checkout on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      "/demo/runtime/admin/settings/payments/balance?mock=user-balance&theme_preview=dark"
    );
    const provider = page.locator(".admin-settings-subsection").filter({
      has: page.locator('[data-settings-anchor="settings-subsection:payments:balance"]'),
    });
    const body = page.locator(".admin-settings-subsection-body").filter({
      has: page.locator('[data-settings-anchor="settings-field:USER_BALANCE_RECURRING_ENABLED"]'),
    });
    await expect(body).toBeVisible();
    await expect(body.getByRole("switch", { name: "Автопродление с баланса" })).toHaveAttribute(
      "aria-checked",
      "false"
    );
    await expect(provider).toContainText("💸");
    const balanceIcon = provider.locator(".admin-provider-logo-emoji");
    await expect(balanceIcon).toHaveCSS("width", "32px");
    await expect(balanceIcon).toHaveCSS("font-size", "30px");
    await expect(balanceIcon.locator("span")).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    await expect(balanceIcon.locator("span")).toHaveCSS("border-top-width", "0px");
    if (device === "mobile") {
      await page.screenshot({ path: path.join(screenshots, "after-settings-mobile-top.png") });
      await body
        .locator('[data-settings-anchor="settings-field:USER_BALANCE_RECURRING_ENABLED"]')
        .scrollIntoViewIfNeeded();
    }
    await page.screenshot({ path: path.join(screenshots, `after-settings-${device}.png`) });
    await body.getByRole("button", { name: "Настройки партнёрки" }).click();
    await expect(page.getByRole("button", { name: "Провайдер «Баланс»" })).toBeVisible();
    await page.getByRole("button", { name: "Провайдер «Баланс»" }).click();
    await expect(body).toBeVisible();

    await page.goto(checkout);
    const balance = page.locator(".balance-discount");
    await expect(balance).toBeVisible();
    const picker = page.locator(".payment-method-select-trigger");
    await expect(picker).toBeEnabled();
    await expect(balance.locator(".balance-recurring-row")).toHaveCount(0);
    const collapsedHeight = (await balance.boundingBox())!.height;
    await balance.getByRole("checkbox").click();
    const recurring = balance.getByRole("switch", { name: "Автопродление с баланса" });
    await expect(recurring).toBeEnabled();
    expect(
      await balance.locator(".balance-recurring-row").evaluate(async (node) => {
        await new Promise(requestAnimationFrame);
        return node
          .getAnimations()
          .some((animation) => Number(animation.effect?.getComputedTiming().duration) > 0);
      })
    ).toBe(true);
    await expect(recurring).toHaveAttribute("aria-checked", "true");
    await expect(picker).toBeVisible();
    await expect(picker).toBeDisabled();
    await expect(picker).toContainText("Tribute");
    await expect(page.locator("body")).not.toContainText("Внешняя оплата не требуется");
    await expect
      .poll(async () => (await balance.boundingBox())!.height)
      .toBeGreaterThan(collapsedHeight + 25);
    await balance.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(screenshots, `after-checkout-${device}.png`) });
    await balance.getByRole("button", { name: "Как работает автопродление с баланса" }).click();
    await expect(page.locator(".balance-recurring-popover")).toContainText(
      "только с выбранного баланса"
    );
    await page.screenshot({ path: path.join(screenshots, `after-help-${device}.png`) });
    await page.keyboard.press("Escape");
    await expect(page.locator(".balance-recurring-popover")).toHaveCount(0);
    await balance.locator(".balance-source-trigger").click();
    await page.getByRole("option", { name: /Партнёрский баланс/ }).click();
    await expect(balance.locator(".balance-source-trigger")).toHaveText("баланса партнёрки");
    await expect(recurring).toHaveAttribute("aria-checked", "true");
    await recurring.click();
    await expect(recurring).toHaveAttribute("aria-checked", "false");
    await recurring.click();
    await expect(recurring).toHaveAttribute("aria-checked", "true");
    const expandedHeight = (await balance.boundingBox())!.height;
    await balance.getByRole("checkbox").click();
    expect(
      await balance.locator(".balance-recurring-row").evaluate(async (node) => {
        await new Promise(requestAnimationFrame);
        return node
          .getAnimations()
          .some((animation) => Number(animation.effect?.getComputedTiming().duration) > 0);
      })
    ).toBe(true);
    await expect(balance.locator(".balance-recurring-row")).toHaveCount(0);
    await expect(picker).toBeEnabled();
    await expect(balance.locator(".balance-source-trigger")).toBeVisible();
    expect((await balance.boundingBox())!.height).toBeLessThan(expandedHeight - 25);
    await balance.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: path.join(screenshots, `after-checkout-collapsed-${device}.png`),
    });
    expect(errors).toEqual([]);
  });

  test(`fully funded balance disables provider buttons on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.addInitScript(() => {
      sessionStorage.setItem(
        "minishop-demo-settings-changes",
        JSON.stringify([["PAYMENT_METHODS_DISPLAY_MODE", { value: "buttons", deleted: false }]])
      );
    });
    await page.goto(checkout);
    const balance = page.locator(".balance-discount");
    const providers = page.locator(".method-grid");
    await expect(providers.getByRole("button", { name: "Tribute", exact: true })).toBeEnabled();
    await balance.getByRole("checkbox").click();
    await expect(providers).toBeVisible();
    for (const provider of await providers.getByRole("button").all()) {
      await expect(provider).toBeDisabled();
    }
    await expect(balance.locator(".balance-source-trigger")).toBeVisible();
    await balance.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(screenshots, `after-checkout-buttons-${device}.png`) });
    await balance.getByRole("checkbox").click();
    await expect(providers.getByRole("button", { name: "Tribute", exact: true })).toBeEnabled();
  });

  for (const method of ["Tribute", "Telegram Stars", "WATA", "OxaPay"]) {
    test(`balance uses monetary limits after ${method} on ${device}`, async ({ page }) => {
      await page.setViewportSize(viewport);
      await page.goto(
        checkout.replace("mock=balance-recurring", "mock=balance-recurring-methods") +
          "&tgWebAppVersion=8.0"
      );
      const picker = page.locator(".payment-method-select-trigger");
      if (method !== "Tribute") {
        await picker.click();
        await page.getByRole("option", { name: method, exact: true }).click();
      }
      await expect(picker).toContainText(method);
      const balance = page.locator(".balance-discount");
      await balance.getByRole("checkbox").click();
      await expect(picker).toBeDisabled();
      await expect(picker).toContainText(method);
      const renewal = page.getByRole("checkbox", {
        name: "Продлить дополнительные устройства вместе с подпиской",
      });
      await expect(renewal).toBeVisible();
      await expect(page.locator(".hwid-renewal-option")).toContainText("40 ₽");
      const price = page.locator(".period-card.active .animated-price").first();
      await expect(price).toHaveAttribute("aria-label", "330 ₽");
      await expect(page.locator(".wata-subscription-contacts")).toHaveCount(0);
      await expect(page.locator(".payment-submit-button").last()).toBeEnabled();
      await expect(balance.getByRole("switch")).toHaveAttribute("aria-checked", "true");
      await renewal.click();
      await expect(price).toHaveAttribute("aria-label", "290 ₽");
      await page.locator(".checkout-tariff-toggle").click();
      const sliders = page.locator(".checkout-tariff-card").getByRole("slider");
      await sliders.first().press("End");
      await expect(sliders.first()).toHaveAttribute("aria-valuenow", "5");
      await sliders.nth(1).press("End");
      await expect(sliders.nth(1)).toHaveAttribute("aria-valuenow", "4");
      await expect(price).toHaveAttribute("aria-label", "1081 ₽");
      await page.locator(".checkout-promo-input").fill("SAVE20");
      await page.locator(".checkout-promo-action .btn").click();
      await expect(page.locator(".checkout-promo-input")).toHaveAttribute("readonly", "");
      await expect(
        page.locator(".period-card.active .promo-price-pair b .animated-price")
      ).toHaveAttribute("aria-label", "864.8 ₽");
      await expect(picker).toContainText(method);
      await expect(page.locator(".checkout-tariff-card")).not.toContainText("⭐");
      await expect(page.locator(".payment-submit-button").last()).toBeEnabled();
      await expect(balance.getByRole("switch")).toBeEnabled();
      await balance.scrollIntoViewIfNeeded();
      if (method === "Telegram Stars") {
        await page.screenshot({
          path: path.join(screenshots, `after-checkout-stars-balance-${device}.png`),
        });
      }
    });
  }
}

test("partial balance retains the required external recurring provider fields", async ({
  page,
}) => {
  await page.goto(
    checkout.replace("mock=balance-recurring", "mock=balance-recurring-methods-partial")
  );
  const picker = page.locator(".payment-method-select-trigger");
  await picker.click();
  await page.getByRole("option", { name: "WATA", exact: true }).click();
  await page.locator(".balance-discount").getByRole("checkbox").click();
  await expect(picker).toBeEnabled();
  await expect(picker).toContainText("WATA");
  const contacts = page.locator(".wata-subscription-contacts");
  await expect(contacts).toBeVisible();
  await expect(page.locator(".payment-submit-button").last()).toBeDisabled();
  await contacts.locator('input[type="email"]').fill("test@example.com");
  await contacts.locator('input[type="tel"]').fill("+79991234567");
  await expect(page.locator(".payment-submit-button").last()).toBeEnabled();
  await expect(page.locator(".balance-discount").getByRole("switch")).toBeDisabled();
});

test("balance card respects reduced motion when expanding and collapsing", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto(checkout);
  const balance = page.locator(".balance-discount");
  await balance.getByRole("checkbox").click();
  const recurring = balance.locator(".balance-recurring-row");
  await expect(recurring).toBeVisible();
  expect(await recurring.evaluate((node) => node.getAnimations().length)).toBe(0);
  expect(
    await balance
      .locator(".balance-recurring-thumb")
      .evaluate((node) => getComputedStyle(node).transitionDuration)
  ).toBe("0s");
  await balance.getByRole("checkbox").click();
  await expect(recurring).toHaveCount(0);
  await expect(page.locator(".payment-method-select-trigger")).toBeEnabled();
});

test("partial funding and gift checkout never enable recurring balance", async ({ page }) => {
  await page.goto(checkout.replace("mock=balance-recurring", "mock=balance-recurring-partial"));
  const balance = page.locator(".balance-discount");
  await balance.getByRole("checkbox").click();
  const recurring = balance.getByRole("switch", { name: "Автопродление с баланса" });
  await expect(recurring).toBeDisabled();
  await expect(recurring).toHaveAttribute("aria-checked", "false");
  await expect(balance).toContainText("полностью покрывать период");
  await page.goto(
    "/demo/runtime/app/?path=/home&mock=balance-recurring&gift_demo=empty&theme_preview=dark"
  );
  await page.locator(".bottom-nav").getByRole("button", { name: "Бонусы", exact: true }).click();
  await page.locator(".gift-entry .gift-intro button").click();
  await expect(page.locator(".dialog-card.payment-dialog-card")).toBeVisible();
  await expect(page.locator(".dialog-card.payment-dialog-card .balance-discount")).toBeVisible();
  await expect(page.locator(".balance-recurring-row")).toHaveCount(0);
});

test("partner recurrence remains available when personal balance recurrence is disabled", async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      "minishop-demo-settings-changes",
      JSON.stringify([["USER_BALANCE_ENABLED", { value: false, deleted: false }]])
    );
  });
  await page.goto(checkout);
  const balance = page.locator(".balance-discount");
  await balance.getByRole("checkbox").click();
  const recurring = balance.getByRole("switch", { name: "Автопродление с баланса" });
  await expect(recurring).toBeDisabled();
  await expect(balance).toContainText("для выбранного источника отключено");
  await balance.locator(".balance-source-trigger").click();
  await page.getByRole("option", { name: /Партнёрский баланс/ }).click();
  await expect(recurring).toBeEnabled();
});
