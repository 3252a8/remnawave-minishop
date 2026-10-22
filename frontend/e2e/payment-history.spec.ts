import { expect, test, type Page } from "@playwright/test";

async function expectCurrentPage(page: Page, number: number) {
  const pages = page.locator(".webapp-pagination .admin-pagination-page");
  await expect(page.locator(".webapp-pagination [aria-current='page']")).toHaveText(String(number));
  await expect(page.locator(".webapp-pagination [aria-current='page']")).toHaveCount(1);
  const colors = await pages.evaluateAll((buttons) =>
    buttons.map((button) => ({
      active: button.getAttribute("aria-current") === "page",
      background: getComputedStyle(button).backgroundColor,
    }))
  );
  const selectedColor = colors.find((button) => button.active)?.background;
  expect(selectedColor).toBeDefined();
  expect(colors.filter((button) => !button.active).length).toBeGreaterThan(0);
  for (const button of colors.filter((button) => !button.active)) {
    expect(button.background).not.toBe(selectedColor);
  }
}

for (const width of [1440, 390]) {
  test.describe(`payment history at ${width}px`, () => {
    test.use({ hasTouch: width <= 720 });
    test(`payment history opens from settings and paginates at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.goto("/demo/runtime/settings?theme_preview=dark");
      await expect(page.locator(".settings-row-payments svg").first()).toHaveClass(
        /lucide-credit-card-check/
      );
      await expect(page.locator(".settings-links-block .settings-divider")).toHaveCount(0);
      await page.locator(".settings-row-payments").click();
      await expect(page).toHaveURL(/\/settings\/payments/);
      await expect(
        page.getByRole("heading", { name: "История платежей", exact: true })
      ).toBeVisible();
      const rows = page.locator("[data-payment-history-id]");
      await expect(rows).toHaveCount(10);
      await expectCurrentPage(page, 1);
      const paginationHeights = await page
        .locator(".webapp-pagination input, .webapp-pagination button")
        .evaluateAll((nodes) =>
          nodes
            .filter((node) => node.getClientRects().length)
            .map((node) => node.getBoundingClientRect().height)
        );
      expect(paginationHeights.length).toBeGreaterThan(2);
      expect(Math.max(...paginationHeights) - Math.min(...paginationHeights)).toBeLessThanOrEqual(
        1
      );
      const processingStatus = page.getByRole("button", {
        name: "Обрабатывается провайдером",
        exact: true,
      });
      const processingHint = "Провайдер проверяет платёж. Подтверждение оплаты ещё не получено.";
      await expect(processingStatus).toBeVisible();
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      await expect(page.getByText(processingHint, { exact: true })).toBeHidden();
      if (width > 720) {
        await processingStatus.hover();
        await expect(page.getByRole("tooltip")).toHaveText(processingHint);
        await page.keyboard.press("Escape");
        await expect(page.getByRole("tooltip")).toHaveCount(0);
      }
      if (width > 720) await processingStatus.click();
      else await processingStatus.tap();
      await expect(page.getByRole("tooltip")).toHaveText(processingHint);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      const creditingStatus = page.getByRole("button", { name: "Начисляем покупку", exact: true });
      await creditingStatus.focus();
      await expect(page.getByRole("tooltip")).toHaveText(
        "Оплата подтверждена. Покупка ещё начисляется на ваш аккаунт."
      );
      await page.keyboard.press("Escape");
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      await creditingStatus.press("Enter");
      await expect(page.getByRole("tooltip")).toHaveText(
        "Оплата подтверждена. Покупка ещё начисляется на ваш аккаунт."
      );
      await page.keyboard.press("Escape");
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      const awaitingStatus = page.getByRole("link", { name: "Ожидает оплаты", exact: true });
      const checkoutUrl = "https://example.com/checkout/mock-payment-history";
      await expect(awaitingStatus).toHaveAttribute("href", checkoutUrl);
      await expect(awaitingStatus).toHaveAttribute("target", "_blank");
      await expect(awaitingStatus).toHaveAttribute("rel", "noopener noreferrer");
      await expect(
        page.locator("[data-payment-history-id] a.payment-history-status-trigger")
      ).toHaveCount(1);
      await awaitingStatus.focus();
      await expect(page.getByRole("tooltip")).toHaveText(
        "Если вы уже оплатили, ожидаем подтверждения провайдера. После подтверждения покупка будет начислена автоматически."
      );
      await page
        .context()
        .route(checkoutUrl, (route) =>
          route.fulfill({ contentType: "text/plain", body: "Mock checkout" })
        );
      const [checkoutPage] = await Promise.all([
        page.waitForEvent("popup"),
        width > 720 ? awaitingStatus.click() : awaitingStatus.tap(),
      ]);
      await expect(checkoutPage).toHaveURL(checkoutUrl);
      await checkoutPage.close();
      await page.keyboard.press("Escape");
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      const firstId = await rows.first().getAttribute("data-payment-history-id");
      await page.getByRole("button", { name: "Далее", exact: true }).click();
      await expect(rows.first()).not.toHaveAttribute("data-payment-history-id", firstId!);
      await expect(rows).toHaveCount(3);
      await expectCurrentPage(page, 2);
      await page.getByRole("button", { name: "Назад", exact: true }).first().click();
      await expect(page.locator(".settings-row-payments")).toBeVisible();
      const sidebar = page.locator(
        ".rail-settings-subnav [data-webapp-action='open-payment-history']"
      );
      if (width > 720) {
        await expect(sidebar).toBeVisible();
        await expect(sidebar.locator("svg")).toHaveClass(/lucide-credit-card-check/);
        await sidebar.click();
        await expect(
          page.getByRole("heading", { name: "История платежей", exact: true })
        ).toBeVisible();
      } else {
        await expect(sidebar).toBeHidden();
      }
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
      expect(errors).toEqual([]);
    });

    test(`payment history empty and failed states at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(
        "/demo/runtime/app/?startapp=payment-history&mock=payment-history-empty&theme_preview=dark"
      );
      await expect(page).toHaveURL(/\/settings\/payments(?:\?|$)/);
      await expect(page.getByRole("heading", { name: "Платежей пока нет" })).toBeVisible();
      await expect(page.locator("[data-payment-history-id]")).toHaveCount(0);
      await page.goto(
        "/demo/runtime/settings/payments?mock=payment-history-error&theme_preview=dark"
      );
      await expect(page.getByRole("alert")).toHaveText(
        "Не удалось загрузить историю платежей. Попробуйте ещё раз."
      );
      await page.getByRole("button", { name: "Повторить", exact: true }).click();
      await expect(page.getByRole("alert")).toBeVisible();
      await expect(page.locator("[data-payment-history-id]")).toHaveCount(0);
    });
  });
}

for (const width of [1440, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`payment history localizes top-ups and retains failed payments at ${width}px in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript((lang) => {
        localStorage.setItem("rw_minishop_demo_language", lang);
      }, language);
      await page.goto("/demo/runtime/settings/payments?theme_preview=dark");
      await expect(
        page.getByText(language === "ru" ? "Пополнение баланса" : "Balance top-up", { exact: true })
      ).toBeVisible();
      const failed = page.locator("[data-payment-history-id]").filter({
        has: page.getByRole("button", {
          name: language === "ru" ? "Платёж не завершён" : "Payment incomplete",
          exact: true,
        }),
      });
      await expect(failed).toHaveCount(1);
      await expectCurrentPage(page, 1);
      await page.screenshot({
        path: testInfo.outputPath(`payment-history-${width}-${language}.png`),
      });
    });
  }
}

for (const width of [1440, 780, 390]) {
  test.describe(`payment history geometry at ${width}px`, () => {
    test(`payment history keeps list geometry during updates at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.addInitScript(() => {
        const setTimeout = window.setTimeout.bind(window);
        window.setTimeout = (handler, timeout, ...args) =>
          setTimeout(handler, timeout === 120 ? 800 : timeout, ...args);
      });
      await page.goto("/demo/runtime/settings/payments?theme_preview=dark");
      const list = page.locator(".payment-history-list");
      const rows = page.locator("[data-payment-history-id]");
      await expect(list).toHaveAttribute("aria-busy", "false");
      await expect(rows).toHaveCount(10);
      const geometry = () =>
        list.evaluate((element) => ({
          top: element.offsetTop,
          height: element.getBoundingClientRect().height,
        }));
      const initial = await geometry();
      const expectStableList = async () => {
        const current = await geometry();
        expect(Math.abs(current.top - initial.top)).toBeLessThanOrEqual(1);
        expect(Math.abs(current.height - initial.height)).toBeLessThanOrEqual(1);
      };
      const expectLoading = async () => {
        await expect(list).toHaveAttribute("aria-busy", "true");
        await expect(list.getByRole("status")).toHaveText("Загрузка...");
        await expect(list.locator(".payment-history-skeleton .ui-skeleton").first()).toBeVisible();
        await expect(rows.first()).toBeHidden();
        await expectStableList();
      };

      await page.getByRole("button", { name: "Далее", exact: true }).click();
      await expectLoading();
      await list.scrollIntoViewIfNeeded();
      const loadingShot = test.info().outputPath(`payment-history-loading-${width}.png`);
      await page.screenshot({ path: loadingShot });
      await test.info().attach(`payment-history-loading-${width}`, {
        path: loadingShot,
        contentType: "image/png",
      });
      await expect(list).toHaveAttribute("aria-busy", "false");
      await expect(rows).toHaveCount(3);
      await expectStableList();

      const refresh = page.locator(".payment-history-heading button");
      await page.evaluate(() => {
        const url = new URL(location.href);
        url.searchParams.set("mock", "payment-history-empty");
        history.replaceState(history.state, "", url);
      });
      await refresh.click();
      await expectLoading();
      await expect(page.getByRole("heading", { name: "Платежей пока нет" })).toBeVisible();
      await expect(rows).toHaveCount(0);
      await expectStableList();
      const emptyShot = test.info().outputPath(`payment-history-empty-${width}.png`);
      await page.screenshot({ path: emptyShot });
      await test.info().attach(`payment-history-empty-${width}`, {
        path: emptyShot,
        contentType: "image/png",
      });
      await refresh.click();
      await expect(list).toHaveAttribute("aria-busy", "true");
      await expect(page.getByRole("heading", { name: "Платежей пока нет" })).toBeHidden();
      await expectStableList();
      await expect(list).toHaveAttribute("aria-busy", "false");
      await expectStableList();

      await page.evaluate(() => {
        const url = new URL(location.href);
        url.searchParams.set("mock", "payment-history-error");
        history.replaceState(history.state, "", url);
      });
      await refresh.click();
      await expect(list).toHaveAttribute("aria-busy", "false");
      await expect(list.getByRole("alert")).toBeVisible();
      await expectStableList();
      await page.getByRole("button", { name: "Повторить", exact: true }).click();
      await expect(list).toHaveAttribute("aria-busy", "true");
      await expectStableList();
      await expect(list).toHaveAttribute("aria-busy", "false");
      await expect(list.getByRole("alert")).toBeVisible();
      await expectStableList();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
      ).toBeLessThanOrEqual(2);
    });
  });
}
