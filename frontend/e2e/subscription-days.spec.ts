import { expect, test, type Page } from "@playwright/test";

async function openTopup(page: Page, devices: boolean, scenario = "eligible", theme = "dark") {
  await page.goto(
    `/demo/runtime/${devices ? "devices" : "home"}?mock=${devices ? "devices" : "depleted"}&subscription_days=${scenario}&theme_preview=${theme}`
  );
  await page
    .locator(`[data-webapp-action="open-${devices ? "device" : "regular"}-topup"]:visible`)
    .first()
    .click();
  const dialog = page.locator(devices ? ".webapp-device-topup-dialog" : ".webapp-topup-dialog");
  await expect(
    dialog.locator(scenario === "buttons" ? ".method-grid" : ".payment-method-select-trigger")
  ).toBeVisible();
  return dialog;
}

async function dayAttempts(page: Page): Promise<Record<string, unknown>[]> {
  return page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("minishop.demo.subscriptionDaysAttempts") || "[]")
  );
}

for (const width of [390, 1440]) {
  for (const language of ["ru", "en"] as const) {
    const theme = language === "ru" ? "dark" : "light";
    const dayMethod = language === "ru" ? "Оплатить днями подписки" : "Pay with subscription days";
    for (const devices of [false, true]) {
      test(`subscription days ${devices ? "devices" : "traffic"} at ${width}px in ${language}`, async ({
        page,
      }, testInfo) => {
        await page.setViewportSize({ width, height: 900 });
        await page.addInitScript(
          (lang) => localStorage.setItem("rw_minishop_demo_language", lang),
          language
        );
        const errors: string[] = [];
        page.on("pageerror", (error) => errors.push(error.message));
        const dialog = await openTopup(page, devices, "eligible", theme);
        if (devices) {
          await expect(dialog.locator(".option-row.plan-row").first()).toContainText(
            language === "ru" ? "+1 устройство" : "+1 device"
          );
          await expect(dialog.locator(".option-row.plan-row").nth(1)).toContainText(
            language === "ru" ? "+3 устройства" : "+3 devices"
          );
        }
        const picker = dialog.locator(".payment-method-select-trigger");
        const moneyMethod = (await picker.innerText()).trim();
        await picker.click();
        await page.getByRole("option", { name: dayMethod, exact: true }).click();
        await expect(dialog.locator(".subscription-days-quote")).toContainText(
          language === "ru" ? "К списанию: 4 дн." : "Days to spend: 4"
        );
        await expect(dialog.locator(".subscription-days-dates")).toContainText("31");
        await expect(dialog.locator(".subscription-days-dates")).toContainText("27");
        await expect(dialog.locator('input[name$="checkout-code"]')).toHaveCount(0);
        await dialog.locator(".option-row.plan-row").nth(1).click();
        await expect(dialog.locator(".subscription-days-heading")).toContainText("10");
        await dialog.locator(".option-row.plan-row").first().click();
        await picker.click();
        await page.getByRole("option", { name: moneyMethod, exact: true }).click();
        await expect(dialog.locator('input[name$="checkout-code"]')).toBeVisible();
        await picker.click();
        await page.getByRole("option", { name: dayMethod, exact: true }).click();
        const pay = dialog.locator(".payment-submit-button");
        await expect(pay).toBeEnabled();
        await expect(page.locator(".payment-method-select-content")).toHaveCount(0);
        await pay.scrollIntoViewIfNeeded();
        expect(
          await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)
        ).toBe(true);
        await page.screenshot({
          path: testInfo.outputPath(
            `days-${devices ? "devices" : "traffic"}-${width}-${language}-${theme}.png`
          ),
        });
        await pay.click();
        await expect(dialog).toHaveCount(0);
        await expect.poll(async () => (await dayAttempts(page)).length).toBe(1);
        const [body] = await dayAttempts(page);
        expect(body.method).toBe("subscription_days");
        expect(body.quote_token).toBeTruthy();
        expect(body).not.toHaveProperty("balance_source");
        expect(body).not.toHaveProperty("promo_code");
        expect(errors).toEqual([]);
      });
    }

    test(`subscription days history and settings at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript(
        (lang) => localStorage.setItem("rw_minishop_demo_language", lang),
        language
      );
      await page.goto(
        `/demo/runtime/settings/payments?subscription_days=eligible&theme_preview=${theme}`
      );
      const purchase = page.locator('[data-payment-history-id="118000"]');
      await expect(purchase).toContainText(language === "ru" ? "0 ₽ · 4 дн." : "0 ₽ · 4 days");
      await expect(purchase).toContainText(
        language === "ru" ? "Дни подписки" : "Subscription days"
      );
      const providerName = purchase.locator(".admin-payment-provider-name");
      expect(
        await providerName.evaluate((element) => {
          const lineHeight = Number.parseFloat(getComputedStyle(element).lineHeight);
          return (
            element.scrollWidth <= element.clientWidth + 1 &&
            element.getBoundingClientRect().height <= lineHeight * 2 + 1
          );
        })
      ).toBe(true);
      await page.screenshot({
        path: testInfo.outputPath(`days-history-${width}-${language}-${theme}.png`),
      });
      const refunded = page.locator('[data-payment-history-id="118001"]');
      await refunded.locator(".payment-history-status-trigger").click();
      await expect(
        page
          .getByRole("tooltip")
          .filter({ hasText: language === "ru" ? "Возвращено дней" : "days returned" })
      ).toBeVisible();
      await page.goto(
        `/demo/runtime/admin/settings/payments/subscription_days?subscription_days=eligible&theme_preview=${theme}`
      );
      for (const key of [
        "SUBSCRIPTION_DAYS_DEVICES_ENABLED",
        "SUBSCRIPTION_DAYS_TRAFFIC_ENABLED",
        "SUBSCRIPTION_DAYS_MIN_REMAINING",
      ]) {
        await expect(page.locator(`[data-settings-anchor="settings-field:${key}"]`)).toBeVisible();
      }
      await expect(
        page.locator(
          '[data-settings-anchor="settings-field:SUBSCRIPTION_DAYS_MIN_REMAINING"] input'
        )
      ).toHaveValue("1");
      await page.screenshot({
        path: testInfo.outputPath(`days-settings-${width}-${language}-${theme}.png`),
      });
    });
  }

  test(`subscription days reversal explains the day refund at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/payments?subscription_days=eligible&theme_preview=dark");
    const row =
      width < 768
        ? page.locator('[data-mobile-payment-id="118000"]')
        : page.locator(".admin-payments-table tbody tr").filter({ hasText: "#118000" });
    await expect(row).toContainText("0 ₽ · 4 дн.");
    if (width < 768) {
      for (const paymentId of [118000, 118001]) {
        const status = page.locator(
          `[data-mobile-payment-id="${paymentId}"] .admin-payment-mobile-head .admin-badge`
        );
        expect(
          await status.evaluate((element) => {
            const range = document.createRange();
            range.selectNodeContents(element);
            return range.getClientRects().length;
          })
        ).toBe(1);
      }
    }
    await page.screenshot({
      path: testInfo.outputPath(`days-admin-payments-${width}.png`),
      animations: "disabled",
    });
    await row.locator(".admin-payment-id-btn").click();
    const dialog = page.locator(".admin-payment-dialog");
    await expect(dialog.locator(".admin-payment-summary-meta > strong")).toContainText(
      "0 ₽ · 4 дн."
    );
    await page.screenshot({
      path: testInfo.outputPath(`days-payment-detail-${width}.png`),
      animations: "disabled",
    });
    await expect(dialog.getByText("hwid_devices", { exact: true })).toHaveCount(0);
    await dialog.getByRole("button", { name: "Отменить платёж", exact: true }).click();
    await expect(dialog).toContainText("4 дн. вернутся к сроку подписки");
    await expect(dialog.getByText("Вернуть использование промокоду", { exact: true })).toHaveCount(
      0
    );
    await dialog.locator(".admin-payment-action-buttons").last().scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath(`days-reversal-${width}.png`) });
    await dialog
      .locator(".admin-payment-action-reason textarea")
      .fill("Проверка возврата дней подписки");
    await dialog.getByRole("button", { name: "Подтвердить", exact: true }).click();
    await expect(dialog.getByRole("button", { name: "Подтвердить", exact: true })).toHaveCount(0);
    await expect
      .poll(() =>
        page.evaluate(() =>
          JSON.parse(sessionStorage.getItem("minishop.demo.subscriptionDaysReverse") || "null")
        )
      )
      .toMatchObject({ restore_promo_usage: false, refund_to_balance: false });
    await expect(dialog.getByRole("button", { name: "Отменить платёж", exact: true })).toHaveCount(
      0
    );
  });
}

test("subscription days stale quote requires another explicit confirmation", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const dialog = await openTopup(page, false, "stale");
  await dialog.locator(".payment-method-select-trigger").click();
  await page.getByRole("option", { name: "Оплатить днями подписки", exact: true }).click();
  await dialog.locator(".payment-submit-button").click();
  await expect(dialog.locator(".subscription-days-heading")).toContainText("5 дн.");
  expect(await dayAttempts(page)).toHaveLength(1);
  await expect(dialog.locator(".payment-submit-button")).toBeEnabled();
  const staleToast = page.locator(".app-toast").filter({ hasText: "Расчёт обновлён." });
  await expect(staleToast).toHaveCSS("opacity", "1");
  await staleToast.evaluate(async (element) => {
    await Promise.all(element.getAnimations().map((animation) => animation.finished));
  });
  const toastBounds = await staleToast.boundingBox();
  expect(toastBounds).not.toBeNull();
  expect(toastBounds!.y + toastBounds!.height).toBeLessThanOrEqual(900);
  await page.screenshot({
    path: testInfo.outputPath("days-stale-390.png"),
    animations: "disabled",
  });
  await dialog.locator(".payment-submit-button").click();
  await expect(dialog).toHaveCount(0);
  expect(await dayAttempts(page)).toHaveLength(2);
});

test("subscription days unavailable reasons remain readable with money payment available", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 768, height: 900 });
  const dialog = await openTopup(page, false, "insufficient_days");
  await expect(dialog.locator(".subscription-days-quote")).toContainText("Недостаточно дней");
  await expect(dialog.locator(".payment-submit-button")).toBeEnabled();
  await dialog.locator(".payment-method-select-trigger").click();
  const disabledMethod = page.getByRole("button", {
    name: /Оплатить днями подписки: Недостаточно дней/,
  });
  await disabledMethod.click();
  await expect(page.getByRole("tooltip")).toContainText("должно остаться не менее 1 дн.");
  await dialog.locator(".payment-method-select-trigger").click();
  await expect(page.locator(".payment-method-select-content")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("days-unavailable-768.png") });
  expect(await dayAttempts(page)).toEqual([]);
});

test("subscription days works with the existing button layout", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const dialog = await openTopup(page, true, "buttons");
  await dialog.getByRole("button", { name: "Оплатить днями подписки", exact: true }).click();
  await expect(dialog.locator(".subscription-days-heading")).toContainText("4 дн.");
  await dialog.locator(".payment-submit-button").scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("days-buttons-390.png") });
  await dialog.locator(".payment-submit-button").click();
  await expect(dialog).toHaveCount(0);
  expect(await dayAttempts(page)).toHaveLength(1);
});

test("subscription days is absent from ordinary subscription checkout", async ({ page }) => {
  await page.goto(
    "/demo/runtime/home?mock=checkout-addons&subscription_days=eligible&theme_preview=dark"
  );
  await page.locator('[data-webapp-action="open-payment"]:visible').first().click();
  const dialog = page.locator(".webapp-payment-dialog");
  const tariffs = dialog.locator(".tariff-row");
  if (await tariffs.count()) {
    await tariffs.first().click();
    await dialog.locator(".payment-submit-button").first().click();
  }
  await dialog.locator(".payment-method-select-trigger").click();
  await expect(
    page.getByRole("option", { name: "Оплатить днями подписки", exact: true })
  ).toHaveCount(0);
});
