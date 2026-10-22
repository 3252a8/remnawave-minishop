import { expect, test, type Page } from "@playwright/test";

async function openCheckout(page: Page) {
  await page.locator('[data-webapp-action="open-payment"]:visible').first().click();
  const dialog = page.locator(".dialog-card.webapp-payment-dialog");
  await expect(dialog).toBeVisible();
  const tariffs = dialog.locator(".tariff-row");
  if (await tariffs.count()) {
    await tariffs.first().click();
    await dialog.locator(".payment-submit-button").first().click();
  }
  await expect(dialog.locator(".payment-method-select-trigger")).toBeVisible();
  return dialog;
}

async function attempts(page: Page): Promise<Record<string, unknown>[]> {
  return page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("minishop.demo.paymentFallbackAttempts") || "[]")
  );
}

for (const width of [390, 1280]) {
  test(`payment fallback preserves the checkout and requires Pay at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      "/demo/runtime/home?mock=checkout-addons&payment_failure=chain&theme_preview=dark"
    );
    let dialog = await openCheckout(page);
    const picker = dialog.locator(".payment-method-select-trigger");
    await expect(picker).toContainText("WATA");
    await dialog.locator(".period-card").nth(1).click();
    await dialog.locator(".checkout-tariff-summary-button").click();
    await dialog.getByRole("slider").first().press("End");
    await dialog.locator(".checkout-promo-input").fill("SAVE20");
    await dialog.locator(".checkout-promo-action .btn").click();
    await expect(dialog.locator(".checkout-promo-input")).toHaveAttribute("readonly", "");
    await dialog.locator('.balance-discount [role="checkbox"]').first().click();
    const pay = dialog.locator(".payment-submit-button").last();
    await expect(pay).toBeEnabled();
    await pay.click();
    const failure = page.locator(".webapp-payment-fallback-dialog");
    const alternative = failure.locator('[data-webapp-action="select-payment-alternative"]');
    await expect(failure).toContainText("WATA");
    await expect(alternative).toContainText("СБП");
    const firstAttempt = (await attempts(page))[0];
    expect(firstAttempt).toMatchObject({
      method: "wata",
      months: 3,
      promo_code: "SAVE20",
      balance_source: "user",
      checkout_addons: { device_count: 5 },
    });
    await alternative.click();
    await expect(picker).toContainText("СБП");
    await expect(failure).toHaveCount(0);
    await expect(pay).toBeEnabled();
    expect(await attempts(page)).toHaveLength(1);
    await expect(dialog.locator(".checkout-promo-input")).toHaveValue("SAVE20");
    await pay.click();
    await expect(failure).toContainText("Других доступных способов этого типа");
    const secondAttempt = (await attempts(page))[1];
    expect(secondAttempt).toEqual({ ...firstAttempt, method: "platega_sbp" });
    await expect(alternative).toHaveCount(0);
    await expect(
      failure.getByRole("button", { name: "Вернуться к оплате", exact: true })
    ).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(failure).toHaveCount(0);
    await expect(pay).toBeEnabled();
    await picker.click();
    await expect(page.getByRole("option", { name: "WATA", exact: true })).toBeEnabled();
    await page.keyboard.press("Escape");
    await dialog.locator(".dialog-close-button").click();
    dialog = await openCheckout(page);
    await expect(failure).toHaveCount(0);
    await dialog.locator(".payment-method-select-trigger").click();
    await page.getByRole("option", { name: "WATA", exact: true }).click();
    await dialog.locator(".payment-submit-button").last().click();
    await expect(alternative).toContainText("СБП");
    expect(errors).toEqual([]);
  });
}

test("a single method can be retried and validation failures keep the existing error flow", async ({
  page,
}) => {
  await page.goto("/demo/runtime/home?mock=checkout-addons&payment_failure=only");
  let dialog = await openCheckout(page);
  await dialog.locator(".payment-submit-button").last().click();
  const failure = page.locator(".webapp-payment-fallback-dialog");
  await expect(failure).toContainText("Других доступных способов");
  await failure.getByRole("button", { name: "Вернуться к оплате", exact: true }).click();
  await expect(failure).toHaveCount(0);
  await dialog.locator(".payment-submit-button").last().click();
  await expect.poll(() => attempts(page).then((items) => items.length)).toBe(2);
  await expect(failure).toBeVisible();
  await page.goto("/demo/runtime/home?mock=checkout-addons&payment_failure=validation");
  dialog = await openCheckout(page);
  await dialog.locator(".payment-submit-button").last().click();
  await expect(page.getByText("Invalid plan", { exact: true })).toBeVisible();
  await expect(failure).toHaveCount(0);
});

test("recurring payer contacts survive method selection and late checkout failures are discarded", async ({
  page,
}) => {
  await page.goto("/demo/runtime/home?mock=checkout-addons&payment_failure=contacts");
  const dialog = await openCheckout(page);
  const email = dialog.locator('input[type="email"]');
  const phone = dialog.locator('input[type="tel"]');
  await email.fill("payer@example.com");
  await phone.fill("+79991234567");
  await dialog.locator(".payment-submit-button").last().click();
  await page.locator('[data-webapp-action="select-payment-alternative"]').click();
  await dialog.locator(".payment-method-select-trigger").click();
  await page.getByRole("option", { name: "WATA", exact: true }).click();
  await expect(email).toHaveValue("payer@example.com");
  await expect(phone).toHaveValue("+79991234567");
  await expect(dialog.locator(".payment-submit-button").last()).toBeEnabled();
  // Close in the same event loop turn, before the failure modal can block background controls.
  await dialog.evaluate((element) => {
    const pay = Array.from(
      element.querySelectorAll<HTMLButtonElement>(".payment-submit-button")
    ).at(-1);
    const close = element.querySelector<HTMLButtonElement>(".dialog-close-button");
    if (!pay || !close) throw new Error("Checkout controls missing");
    pay.click();
    close.click();
  });
  const reopened = await openCheckout(page);
  await expect.poll(() => attempts(page).then((items) => items.length)).toBe(2);
  await expect(reopened).toBeVisible();
  await expect(page.locator(".webapp-payment-fallback-dialog")).toHaveCount(0);
});

for (const flow of ["regular", "device", "balance"]) {
  test(`${flow} top-up offers another method without changing the purchase`, async ({ page }) => {
    const mock =
      flow === "regular" ? "depleted" : flow === "device" ? "devices" : "checkout-addons";
    await page.goto(`/demo/runtime/home?mock=${mock}&payment_failure=chain&theme_preview=dark`);
    if (flow === "device")
      await page
        .locator(".bottom-nav")
        .getByRole("button", { name: "Устройства", exact: true })
        .click();
    const action = flow === "balance" ? "open-balance-topup" : `open-${flow}-topup`;
    await page.locator(`[data-webapp-action="${action}"]:visible`).first().click();
    const selector =
      flow === "balance"
        ? ".balance-topup-dialog"
        : flow === "device"
          ? ".webapp-device-topup-dialog"
          : ".webapp-topup-dialog";
    const dialog = page.locator(`.dialog-card${selector}`);
    await expect(dialog).toBeVisible();
    if (flow === "balance") await dialog.locator(".balance-amount-field input").fill("777");
    const pay = dialog.locator(".payment-submit-button").last();
    await expect(pay).toBeEnabled();
    await pay.click();
    const fallback = page.locator(".webapp-payment-fallback-dialog");
    await expect(fallback).toContainText("WATA");
    await fallback.locator('[data-webapp-action="select-payment-alternative"]').click();
    await expect(fallback).toHaveCount(0);
    await expect(dialog.locator(".payment-method-select-trigger")).toContainText("СБП");
    expect(await attempts(page)).toHaveLength(1);
    if (flow === "balance")
      await expect(dialog.locator(".balance-amount-field input")).toHaveValue("777");
    await expect(pay).toBeEnabled();
    await pay.click();
    await expect(fallback).toContainText("Других доступных способов этого типа");
    await expect(fallback.locator('[data-webapp-action="select-payment-alternative"]')).toHaveCount(
      0
    );
    const purchases = await attempts(page);
    expect(purchases[1]).toEqual({ ...purchases[0], method: "platega_sbp" });
  });
}

for (const width of [390, 1280]) {
  test(`crypto fallback skips fiat and the rejected gateway at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 950 });
    await page.goto(
      "/demo/runtime/home?mock=checkout-addons&payment_failure=crypto&theme_preview=dark"
    );
    const checkout = await openCheckout(page);
    const picker = checkout.locator(".payment-method-select-trigger");
    const pay = checkout.locator(".payment-submit-button").last();
    await expect(picker).toContainText("Crypto Pay");
    await pay.click();
    const modal = page.locator(".webapp-payment-fallback-dialog");
    const alternative = modal.locator('[data-webapp-action="select-payment-alternative"]');
    await expect(alternative).toContainText("Cryptomus");
    await alternative.click();
    await expect(picker).toContainText("Cryptomus");
    await expect(pay).toBeEnabled();
    expect(await attempts(page)).toHaveLength(1);
    await pay.click();
    await expect(modal).toContainText("Других доступных способов этого типа");
    await expect(alternative).toHaveCount(0);
    const purchases = await attempts(page);
    expect(purchases[0].method).toBe("cryptopay");
    expect(purchases[1]).toEqual({ ...purchases[0], method: "cryptomus" });
  });
}

test("unknown payment groups leave the ordinary method picker available", async ({ page }) => {
  await page.goto("/demo/runtime/home?mock=checkout-addons&payment_failure=unknown");
  const checkout = await openCheckout(page);
  await checkout.locator(".payment-submit-button").last().click();
  const modal = page.locator(".webapp-payment-fallback-dialog");
  await expect(modal).toContainText("Других доступных способов этого типа");
  await expect(modal.locator('[data-webapp-action="select-payment-alternative"]')).toHaveCount(0);
  await modal.getByRole("button", { name: "Вернуться к оплате", exact: true }).click();
  await checkout.locator(".payment-method-select-trigger").click();
  await expect(page.getByRole("option", { name: "Crypto Pay", exact: true })).toBeEnabled();
});

for (const width of [390, 1280]) {
  test(`failure modal keeps the form size and restores keyboard focus at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 950 });
    await page.goto("/demo/runtime/home?mock=checkout-addons&payment_failure=chain");
    const checkout = await openCheckout(page);
    await page.evaluate(() => document.fonts.ready);
    const viewport = checkout.locator(".dialog-body-scroll > .scroll-area__viewport");
    const formHeight = await viewport.evaluate((element) => element.scrollHeight);
    const pay = checkout.locator(".payment-submit-button").last();
    await pay.click();
    const modal = page.getByRole("dialog", {
      name: "Способ оплаты временно недоступен",
      exact: true,
    });
    await expect(modal).toHaveAttribute("aria-modal", "true");
    expect(await viewport.evaluate((element) => element.scrollHeight)).toBe(formHeight);
    const alternative = modal.locator('[data-webapp-action="select-payment-alternative"]');
    const back = modal.getByRole("button", { name: "Вернуться к оплате", exact: true });
    await expect(alternative).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(back).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(alternative).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    await expect(checkout).toBeVisible();
    await expect(checkout.locator(".payment-method-select-trigger")).toBeFocused();
    await pay.click();
    await expect(modal).toBeVisible();
    await back.click();
    await expect(modal).toHaveCount(0);
    await expect(checkout.locator(".payment-method-select-trigger")).toBeFocused();
  });
}
