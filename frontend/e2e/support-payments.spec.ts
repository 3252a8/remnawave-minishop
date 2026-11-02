import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  for (const language of ["ru", "en"] as const) {
    test(`billing payment is optional and retained in the draft at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript(
        (lang) => localStorage.setItem("rw_minishop_demo_language", lang),
        language
      );
      await page.goto(
        `/demo/runtime/support/new?theme_preview=${language === "en" ? "light" : "dark"}`
      );
      const screen = page.locator(".support-screen--create");
      await screen
        .getByRole("textbox", { name: language === "ru" ? "Тема" : "Subject", exact: true })
        .fill("Payment question");
      const category = screen.getByRole("combobox", {
        name: language === "ru" ? "Категория" : "Category",
        exact: true,
      });
      await category.click();
      await page
        .getByRole("option", { name: language === "ru" ? "Оплата" : "Billing", exact: true })
        .click();
      const payment = screen.getByRole("combobox", {
        name: language === "ru" ? "Платёж (необязательно)" : "Payment (optional)",
        exact: true,
      });
      await expect(payment).toHaveText(language === "ru" ? "Без платежа" : "No payment");
      await payment.click();
      const choices = page.getByRole("option");
      await expect(choices.nth(1)).toBeVisible();
      const chosen = await choices.nth(1).innerText();
      const screenshot = testInfo.outputPath(`payment-choice-${width}-${language}.png`);
      await page.screenshot({ path: screenshot, animations: "disabled" });
      await testInfo.attach(`payment-choice-${width}-${language}`, {
        path: screenshot,
        contentType: "image/png",
      });
      const dropdown = await page.locator(".support-choice-content").boundingBox();
      expect(dropdown).not.toBeNull();
      expect(dropdown!.x).toBeGreaterThanOrEqual(0);
      expect(dropdown!.x + dropdown!.width).toBeLessThanOrEqual(width);
      await choices.nth(1).click();
      await expect(payment).toHaveText(chosen);
      await page.reload();
      await expect(category).toHaveText(language === "ru" ? "Оплата" : "Billing");
      await expect(payment).toHaveText(chosen);
      await expect(screen.locator(".ticket-composer-send")).toBeInViewport();
      await payment.click();
      await page
        .getByRole("option", {
          name: language === "ru" ? "Без платежа" : "No payment",
          exact: true,
        })
        .click();
      await category.click();
      await page
        .getByRole("option", { name: language === "ru" ? "Техническое" : "Technical", exact: true })
        .click();
      await expect(payment).toHaveCount(0);
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
      ).toBe(true);
      expect(errors).toEqual([]);
    });
  }
}

for (const scenario of ["empty", "error"]) {
  test(`billing ticket can be created without a payment when candidates are ${scenario}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 720 });
    await page.goto(`/demo/runtime/support/new?mock=support-payments-${scenario}`);
    const screen = page.locator(".support-screen--create");
    await screen.getByRole("textbox", { name: "Тема", exact: true }).fill("Payment question");
    await screen.getByRole("combobox", { name: "Категория", exact: true }).click();
    await page.getByRole("option", { name: "Оплата", exact: true }).click();
    await expect(
      screen.getByText(
        scenario === "empty" ? /подходящих платежей нет/ : /Не удалось загрузить платежи/
      )
    ).toBeVisible();
    await screen.locator('[contenteditable="true"]').fill("Please check my payment");
    await screen.locator(".ticket-composer-send").click();
    await expect(page).toHaveURL(/\/support\/\d+/);
  });
}
