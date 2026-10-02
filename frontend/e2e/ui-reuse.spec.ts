import { expect, test, type Locator, type Page } from "@playwright/test";

const adminUrl = (route: string) =>
  `/demo/runtime/admin/${route}?theme_preview=dark&mock=checkout-addons`;

async function noOverflow(element: Locator, vertical = false) {
  const bounds = await element.evaluate((node) => ({
    x: node.scrollWidth - node.clientWidth,
    y: node.scrollHeight - node.clientHeight,
  }));
  expect(bounds.x).toBeLessThanOrEqual(2);
  if (vertical) expect(bounds.y).toBeLessThanOrEqual(2);
}

async function alignedSearch(page: Page) {
  const controls = page.locator(
    ".admin-list-toolbar-search .input, .admin-list-toolbar-search .admin-btn"
  );
  await expect(controls.first()).toBeVisible();
  const heights = await controls.evaluateAll((nodes) =>
    nodes
      .filter((node) => node.getClientRects().length)
      .map((node) => node.getBoundingClientRect().height)
  );
  expect(heights.length).toBeGreaterThanOrEqual(2);
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
}

async function copyFullLink(page: Page, field: Locator) {
  const input = field.locator("input");
  const value = await input.inputValue();
  expect(value).toMatch(/^https:\/\//);
  await input.click();
  expect(
    await input.evaluate((node: HTMLInputElement) => node.selectionEnd! - node.selectionStart!)
  ).toBe(value.length);
  await field.locator("button").first().click();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(value);
  await noOverflow(field);
  const heights = await field
    .locator("input, button")
    .evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().height));
  expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(1);
}

for (const [device, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`promo expiry uses the shared calendar and preserves time on ${device}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto(adminUrl("promos"));
    await page.getByRole("button", { name: "Редактировать", exact: true }).first().click();
    const dialog = page.locator(".admin-promo-edit-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('input[type="datetime-local"]')).toHaveCount(0);
    const trigger = dialog.getByRole("button", { name: "Действует до", exact: true });
    const unlimited = dialog.getByRole("checkbox", { name: "Без ограничения", exact: true });
    await trigger.click();
    const calendar = page.locator(".date-input-popover");
    await expect(calendar).toBeVisible();
    const bounds = await calendar.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    await noOverflow(calendar);
    await calendar.locator(".date-input-day:not([data-outside-month])").nth(15).click();
    await expect(calendar).toBeHidden();
    await trigger.click();
    await expect(calendar).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(calendar).toBeHidden();
    await expect(dialog).toBeVisible();
    await expect(trigger).toBeFocused();
    await dialog.getByRole("button", { name: "Очистить дату: Действует до", exact: true }).click();
    await expect(unlimited).toBeChecked();
    await expect(trigger).toBeDisabled();
    await unlimited.uncheck();
    await expect(trigger).toBeEnabled();
    const field = dialog.locator(".date-input-shell");
    await noOverflow(field.locator(".date-input"));
    for (const [part, value] of Object.entries({
      year: "2031",
      month: "05",
      day: "20",
      hour: "14",
      minute: "30",
    })) {
      await field.locator(`[data-segment="${part}"]`).pressSequentially(value);
    }
    await expect(field.locator('[data-segment="year"]')).toHaveAttribute("aria-valuenow", "2031");
    await expect(field.locator('[data-segment="hour"]')).toHaveAttribute("aria-valuenow", "14");
    await expect(field.locator('[data-segment="minute"]')).toHaveAttribute("aria-valuenow", "30");
    await expect(unlimited).not.toBeChecked();
    await expect(dialog.getByRole("button", { name: "Сохранить", exact: true })).toBeEnabled();
    await noOverflow(dialog);
  });

  test(`guest checkout uses shared email validation on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/demo/runtime/login?mock=auth&plan=standard&theme_preview=dark");
    await expect(page.getByRole("heading", { name: "Укажите email", exact: true })).toBeVisible();
    const email = page.locator('.checkout-card input[type="email"]');
    await expect(email).toHaveClass(/input/);
    await expect(email).toHaveAttribute("autocomplete", "email");
    await email.fill("invalid");
    await email.press("Enter");
    await expect(email).toHaveAttribute("aria-invalid", "true");
    await email.fill("ui-regression@example.test");
    await expect(email).not.toHaveAttribute("aria-invalid", "true");
    await expect(email).toHaveValue("ui-regression@example.test");
    await noOverflow(page.locator(".checkout-card"));
  });

  test(`subscription extension uses the shared calendar on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(
      "/demo/runtime/admin/users/ms_100000000000400080000000000de418?theme_preview=dark"
    );
    const action = page.locator(".admin-user-action-sheet--extend");
    await action.getByRole("button", { name: "Указать дату", exact: true }).click();
    await expect(action.locator('input[type="date"]')).toHaveCount(0);
    const trigger = action.getByRole("button", { name: "Новая дата окончания", exact: true });
    const submit = action.getByRole("button", { name: "Изменить срок", exact: true });
    await expect(submit).toBeDisabled();
    await trigger.press("Enter");
    const calendar = page.locator(".date-input-popover");
    await expect(calendar).toBeVisible();
    await expect(calendar.locator(".date-input-day[data-disabled]").first()).toBeVisible();
    const bounds = await calendar.boundingBox();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
    await noOverflow(calendar);
    const availableDay = calendar.locator(".date-input-day:not([data-disabled])").first();
    const selectedDate = await availableDay.getAttribute("data-value");
    const tomorrow = new Date();
    tomorrow.setUTCDate(tomorrow.getUTCDate() + 1);
    expect(selectedDate! >= tomorrow.toISOString().slice(0, 10)).toBe(true);
    await availableDay.click();
    await page.keyboard.press("Escape");
    await expect(calendar).toBeHidden();
    await expect(trigger).toBeFocused();
    await expect(submit).toBeEnabled();
    await trigger.click();
    await expect(calendar.locator(".date-input-day[data-selected]")).toHaveAttribute(
      "data-value",
      selectedDate!
    );
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await action
      .getByRole("button", { name: "Очистить дату: Новая дата окончания", exact: true })
      .click();
    await expect(submit).toBeDisabled();
    await expect(trigger).toBeFocused();
    await noOverflow(action);
    expect(errors).toEqual([]);
  });

  test(`Telegram merge confirmation fits on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&theme_preview=dark&telegram_auth=account_merge_required"
    );
    const dialog = page.locator(".telegram-merge-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Объединение аккаунтов" })).toBeVisible();
    await expect(dialog.locator(".telegram-merge-form input")).toBeVisible();
    await noOverflow(dialog);
    const bounds = await dialog.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.x).toBeGreaterThanOrEqual(0);
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
  });

  test(`gift navigation initializes from the profile on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const url = (scenario: string) =>
      `/demo/runtime/app/?mock=partner-referral-disabled&theme_preview=dark&gift_demo=${scenario}`;
    const navigation = page.locator(".bottom-nav");
    const bonuses = navigation.getByRole("button", { name: "Бонусы", exact: true });

    // The demo /me response deliberately exposes id, never the admin-only user_id.
    await page.goto(url("empty"));
    await expect(bonuses).toBeVisible();
    await bonuses.click();
    await expect(page.locator(".gift-list")).toContainText("Здесь появятся");
    await expect(
      page.locator(".gift-entry").getByRole("button", { name: "Подарить" })
    ).toBeVisible();

    for (const scenario of ["loading", "error"]) {
      await page.goto(url(scenario));
      await expect(bonuses).toBeVisible();
      await bonuses.click();
      const entry = page.locator(".gift-entry");
      await expect(entry).toBeVisible();
      await expect(entry.getByRole("button", { name: "Подарить" })).toBeVisible();
      if (scenario === "loading")
        await expect(entry.locator(".gift-list")).toContainText("Загрузка");
      else await expect(entry.getByRole("alert")).toBeVisible();
    }

    await page.goto(url("disabled"));
    await expect(bonuses).toBeVisible();
    await bonuses.click();
    await expect(page.locator(".gift-entry .copy-link-field").first()).toBeVisible();
    await expect(page.locator(".gift-entry").getByRole("button", { name: "Подарить" })).toHaveCount(
      0
    );
    await page.goto(url("disabled-empty"));
    await expect(navigation).toBeVisible();
    await expect(navigation.getByRole("button", { name: "Партнёрка", exact: true })).toBeVisible();
    await expect(bonuses).toHaveCount(0);

    await page.goto(`${url("received")}&gift=${"R".repeat(43)}`);
    await expect(page.locator(".gift-dialog")).toBeVisible();
    await expect(
      page.locator(".gift-dialog").getByRole("button", { name: "Активировать подарок" })
    ).toBeVisible();
    expect(errors).toEqual([]);
  });

  test(`bonus cards share corners and spacing on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto(
      "/demo/runtime/app/?mock=checkout-addons&path=/invite&gift_demo=empty&theme_preview=dark"
    );
    await expect(page.locator(".gift-entry")).toBeVisible();
    await expect(page.locator(".gift-entry")).toHaveCSS("background-image", "none");
    const layout = await page.locator("main.content").evaluate((node) => {
      const gift = node.querySelector<HTMLElement>(".gift-entry")!;
      const promo = node
        .querySelector<HTMLElement>(".promo-heading")!
        .closest<HTMLElement>(".card")!;
      const referral = node.querySelector<HTMLElement>(".bonus-card")!;
      return {
        radii: [gift, promo, referral].map((card) => getComputedStyle(card).borderRadius),
        gaps: [
          promo.getBoundingClientRect().top - gift.getBoundingClientRect().bottom,
          referral.getBoundingClientRect().top - promo.getBoundingClientRect().bottom,
        ],
      };
    });
    expect(new Set(layout.radii).size).toBe(1);
    expect(Math.abs(layout.gaps[0] - layout.gaps[1])).toBeLessThanOrEqual(1);
    await noOverflow(page.locator(".gift-entry"));
  });

  test(`remaining admin lists reuse toolbar controls on ${device}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(adminUrl("partners"));
    for (const tab of [1, 2, 3]) {
      await page.locator('.partners-toolbar [role="tab"]').nth(tab).click();
      const toolbar = page.locator(".partner-list-toolbar");
      await expect(toolbar).toBeVisible();
      await alignedSearch(page);
      await expect(toolbar.locator(".admin-field-label > span")).toHaveCSS("font-size", "11px");
      await expect(toolbar.locator(".admin-field-label > span")).toHaveCSS(
        "text-transform",
        "uppercase"
      );
      await noOverflow(toolbar);
      const input = toolbar.locator('input[type="search"]');
      await input.fill("missing-user-example");
      await input.press("Enter");
      await expect(toolbar.locator(".admin-list-toolbar-summary strong")).toHaveText("0");
      await input.fill("");
      await input.press("Enter");
      await expect(toolbar.locator(".admin-list-toolbar-summary strong")).not.toHaveText("0");
      await toolbar.locator(".admin-select-trigger").click();
      await expect(page.getByRole("option").first()).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(toolbar).toBeVisible();
    }
    for (const route of ["logs", "support", "backups"]) {
      await page.goto(adminUrl(route));
      const toolbar = page.locator(".admin-list-toolbar");
      await expect(toolbar).toBeVisible();
      await noOverflow(toolbar);
      if (route === "backups") {
        await toolbar.getByRole("button", { name: "Обновить", exact: true }).click();
        await expect(page.locator(".backups-restore-card")).toBeVisible();
        const radios = page.getByRole("radio");
        const choices = page.locator(".backups-archive-choice");
        await expect(radios).toHaveCount(2);
        await expect(page.getByRole("checkbox", { name: "БД" })).toBeDisabled();
        await choices.nth(1).locator("span").last().click();
        await expect(radios.nth(1)).toBeChecked();
        await expect(page.getByRole("checkbox", { name: "БД" })).toBeEnabled();
        await expect(page.locator(".backups-selected-name")).toHaveText(
          await choices.nth(1).innerText()
        );
        const confirmation = page.locator(".backups-confirmation input");
        await confirmation.fill(await choices.nth(1).innerText());
        await radios.nth(1).press("ArrowUp");
        await expect(radios.first()).toBeChecked();
        await expect(confirmation).toHaveValue("");
        await noOverflow(page.locator(".backups-table"));
        if (device === "mobile") {
          await expect(page.locator(".backups-table thead th")).toHaveCount(3);
          const target = await choices.first().boundingBox();
          expect(target?.height).toBeGreaterThanOrEqual(44);
        }
      } else {
        await alignedSearch(page);
        await toolbar.getByRole("button", { name: "Применить", exact: true }).click();
        if (route === "support") {
          await expect(toolbar.locator(".admin-list-toolbar-summary")).toHaveCount(0);
          if (device === "mobile") {
            await expect(toolbar.locator(".admin-list-toolbar-filters")).toBeHidden();
            await toolbar.getByRole("button", { name: "Фильтры" }).click();
          }
          const filters = page.locator(
            device === "mobile"
              ? ".support-filter-dialog .admin-select-trigger"
              : ".support-list-toolbar .admin-select-trigger"
          );
          await expect(filters).toHaveCount(3);
          for (let index = 0; index < 3; index++) {
            await filters.nth(index).click();
            await expect(page.getByRole("option").first()).toBeVisible();
            await page.keyboard.press("Escape");
          }
          if (device === "mobile") {
            await page.locator(".support-filter-dialog .dialog-close-button").click();
            await page.setViewportSize({ width: 390, height: 460 });
            const content = page.locator(".admin-content");
            const heading = page.locator(".admin-header");
            await expect
              .poll(() =>
                content.evaluate((element) => element.scrollHeight - element.clientHeight)
              )
              .toBeGreaterThan(120);
            const headingTop = await heading.evaluate(
              (element) => element.getBoundingClientRect().top
            );
            await content.evaluate((element) => (element.scrollTop = 120));
            await expect
              .poll(() => heading.evaluate((element) => element.getBoundingClientRect().top))
              .toBeLessThan(headingTop - 60);
            await page.setViewportSize(viewport);
          }
        }
      }
    }
    expect(errors).toEqual([]);
  });

  test(`shared list controls and gift creation remain consistent on ${device}`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize(viewport);
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(adminUrl("users"));
    await expect(page.locator(".admin-users-search-button")).toBeVisible();
    await alignedSearch(page);
    if (device === "mobile") {
      await expect(page.locator(".admin-list-toolbar-filters")).toBeHidden();
      await page.evaluate(() => {
        document.documentElement.style.setProperty("--telegram-fullscreen-fallback-top", "96px");
      });
      await page.locator(".admin-users-filter-toggle").click();
      const dialog = page.locator(".admin-users-filter-dialog");
      await expect(dialog).toBeVisible();
      await dialog.locator(".admin-select-trigger").first().click();
      const menu = page.locator(".admin-select-content[data-state='open']");
      const menuViewport = menu.locator(".admin-select-viewport");
      await expect(page.getByRole("option").first()).toBeVisible();
      const menuBounds = await menu.boundingBox();
      expect(menuBounds).not.toBeNull();
      expect(menuBounds!.y).toBeGreaterThanOrEqual(96);
      expect(menuBounds!.y + menuBounds!.height).toBeLessThanOrEqual(viewport.height - 12);
      const overflow = await menuViewport.evaluate((node) => node.scrollHeight - node.clientHeight);
      expect(overflow).toBeGreaterThan(0);
      await menuViewport.evaluate((node) => {
        node.scrollTop = node.scrollHeight;
      });
      await expect(menu.getByRole("option").last()).toBeInViewport();
      await page.keyboard.press("Escape");
      await expect(dialog).toBeVisible();
      await dialog.locator(".dialog-head button").click();
    }

    await page.goto(adminUrl("gifts"));
    const rows = page.locator(
      device === "desktop" ? ".gift-desktop tbody tr" : ".gift-mobile-card"
    );
    await expect(rows.first()).toBeVisible();
    await alignedSearch(page);
    await expect(page.locator(".admin-list-toolbar-filters")).toBeVisible();
    await page.locator('.gifts-toolbar .admin-select-trigger[aria-label="Источник"]').click();
    await page.getByRole("option", { name: "От администратора", exact: true }).click();
    await expect(rows).toHaveCount(1);
    const provider = rows.first().locator(".admin-payment-provider");
    await expect(provider).toContainText("От администратора");
    await expect(provider.locator(".admin-payment-provider-logo")).toHaveText("🎁");
    await rows.first().locator(".details-toggle").click();
    const details = page.locator(".admin-gift-dialog");
    await expect(details.locator(".admin-payment-provider-logo")).toHaveText("🎁");
    await copyFullLink(page, details.locator(".copy-link-field"));
    await noOverflow(details.locator(".dialog-body-scroll > .scroll-area__viewport"), true);
    await details.locator(".dialog-head button").click();

    await page.getByRole("button", { name: "Создать подарок", exact: true }).click();
    const creation = page.locator(".admin-gift-create-dialog");
    const tariff = creation.locator(".gift-create-plan .admin-select-trigger").first();
    await expect(tariff).toBeVisible();
    const initial = await tariff.innerText();
    await tariff.click();
    await expect(page.getByRole("option").first()).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(creation).toBeVisible();
    await expect(tariff).toHaveText(initial);
    await expect(creation.locator("select")).toHaveCount(0);
    const limits = creation.locator(".gift-create-limits .admin-select-trigger");
    await expect(limits).toHaveCount(3);
    await limits.first().click();
    await page.keyboard.press("End");
    await page.keyboard.press("Enter");
    await creation.locator('input[type="email"]').fill("friend@example.com");
    await noOverflow(creation.locator(".dialog-body-scroll > .scroll-area__viewport"), true);
    await creation.locator('button[type="submit"]').click();
    await expect(details.locator(".copy-link-field")).toBeVisible();
    await expect(details).toContainText("0.00");
    await expect(details).toContainText("friend@example.com");
    await noOverflow(details.locator(".dialog-body-scroll > .scroll-area__viewport"), true);
    await details.locator(".dialog-head button").click();
    await expect(rows).toHaveCount(25);
    const firstRow = await rows.first().innerText();
    await page.getByRole("button", { name: "Далее", exact: true }).click();
    await expect.poll(() => rows.first().innerText()).not.toBe(firstRow);
    await page.locator('.gifts-toolbar input[type="search"]').fill("missing-gift-ui-regression");
    await page.getByRole("button", { name: "Найти", exact: true }).click();
    await expect(page.getByText("Подарки не найдены", { exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });

  test(`shared copy field, payment provider and manual controls render on ${device}`, async ({
    page,
    context,
  }) => {
    await page.setViewportSize(viewport);
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    // Keep the actual UI; seed the operation and both confirmation variants.
    await page.addInitScript(() => {
      type Props = {
        api: (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
      };
      type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
      let bundle: Bundle | undefined;
      Object.defineProperty(window, "SubscriptionWebAppAdmin", {
        configurable: true,
        get: () => bundle,
        set(value: Bundle) {
          const mount = value.mount;
          value.mount = (target, props) =>
            mount(target, {
              ...props,
              api: async (path, options) => {
                const result = await props.api(path, options);
                if (path.split("?")[0] === "/admin/payments" && Array.isArray(result.payments)) {
                  return {
                    ...result,
                    payments: result.payments.map((payment, index) =>
                      index ? payment : { ...payment, provider: "admin_gift", amount: 0 }
                    ),
                  };
                }
                if (/^\/admin\/payments\/\d+$/.test(path) && result.payment) {
                  return {
                    ...result,
                    payment: {
                      ...result.payment,
                      can_manual_finalize: true,
                      can_reverse: true,
                      manual_finalize_requires_promo_confirmation: true,
                      promo_code_id: 14,
                    },
                  };
                }
                return result;
              },
            });
          bundle = value;
        },
      });
    });
    await page.goto(adminUrl("payments"));
    await expect(page.locator(".admin-list-toolbar")).toBeVisible();
    const rows = page.locator(
      device === "desktop" ? ".admin-payments-table tbody tr" : ".admin-payment-mobile-card"
    );
    await expect(rows.first().locator(".admin-payment-provider-name")).toHaveText(
      "От администратора"
    );
    await expect(rows.first().locator(".admin-payment-provider-logo")).toHaveText("🎁");
    await alignedSearch(page);
    const summary = page.locator(".admin-list-toolbar-summary");
    const gap = await summary.evaluate((node) => {
      const label = node.querySelector("span")!.getBoundingClientRect();
      const count = node.querySelector("strong")!.getBoundingClientRect();
      return count.left - label.right;
    });
    expect(gap).toBeLessThanOrEqual(8);
    const search = page.locator('.admin-list-toolbar input[type="search"]');
    await search.fill("not-a-real-user@example.invalid");
    await search.press("Enter");
    await expect(summary.locator("strong")).toHaveText("0");
    await expect(rows).toHaveCount(0);
    await search.fill("");
    await search.press("Enter");
    await expect(rows.first()).toBeVisible();
    await noOverflow(page.locator(".admin-list-toolbar"));
    await rows
      .first()
      .getByRole("button", { name: /Открыть.*плат/ })
      .click();
    const paymentDialog = page.locator(".admin-payment-dialog");
    await paymentDialog.getByRole("button", { name: "Провести платёж", exact: true }).click();
    const reason = paymentDialog.getByRole("textbox", { name: "Причина", exact: true });
    await expect(reason).toHaveClass(/textarea/);
    await expect(reason).toHaveAttribute("maxlength", "500");
    const confirm = paymentDialog.getByRole("button", { name: "Подтвердить", exact: true });
    const conflict = paymentDialog.getByRole("checkbox", { name: /Применить сохранённые условия/ });
    await expect(conflict).toHaveClass(/ui-checkbox/);
    await expect(confirm).toBeDisabled();
    await reason.fill("UI regression reason");
    await expect(confirm).toBeDisabled();
    await conflict.press("Space");
    await expect(conflict).toBeChecked();
    await expect(confirm).toBeEnabled();
    await paymentDialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await paymentDialog.getByRole("button", { name: "Отменить платёж", exact: true }).click();
    const restore = paymentDialog.getByRole("checkbox", {
      name: "Вернуть это использование промокоду",
      exact: true,
    });
    await expect(restore).toHaveClass(/ui-checkbox/);
    await expect(restore).toBeChecked();
    await restore.press("Space");
    await expect(restore).not.toBeChecked();
    await reason.fill("UI regression reason");
    await expect(confirm).toBeEnabled();
    await noOverflow(paymentDialog);
    await paymentDialog.getByRole("button", { name: "Закрыть", exact: true }).last().click();
    await page.goto("/demo/runtime/app/?mock=checkout-addons&path=/invite&theme_preview=dark");
    await expect(page.locator(".gift-entry .copy-link-field").first()).toBeVisible();
    await copyFullLink(page, page.locator(".gift-entry .copy-link-field").first());
    const referralField = page.locator(".bonus-card .copy-link-field").first();
    await copyFullLink(page, referralField);
    await referralField.getByRole("button", { name: /QR/ }).click();
    await expect(page.locator(".link-qr-tile img")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.locator(".link-qr-tile")).toHaveCount(0);
  });
}
