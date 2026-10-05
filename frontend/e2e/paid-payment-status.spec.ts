import { expect, test, type Locator, type TestInfo } from "@playwright/test";

const paidStatuses = ["succeeded_pending_review", "succeeded_pending_finalization"] as const;
const labels = ["Оплачен · нужна проверка", "Оплачен · применяем покупку"];
const adminUrl = (route: string) =>
  `/demo/runtime/admin/${route}?theme_preview=dark&mock=checkout-addons`;

async function noOverflow(element: Locator) {
  expect(await element.evaluate((node) => node.scrollWidth - node.clientWidth)).toBeLessThanOrEqual(
    2
  );
}

async function capture(element: Locator, name: string, testInfo: TestInfo) {
  const path = testInfo.outputPath(`${name}.png`);
  await element.screenshot({ path });
  await testInfo.attach(name, { path, contentType: "image/png" });
}

async function statusFitsCell(badge: Locator) {
  const bounds = await badge.evaluate((element) => {
    const cell = element.closest("td") || element.parentElement!;
    const status = element.getBoundingClientRect();
    const container = cell.getBoundingClientRect();
    const next =
      getComputedStyle(cell).display === "table-cell"
        ? cell.nextElementSibling?.getBoundingClientRect()
        : null;
    return {
      left: status.left - container.left,
      right: status.right - container.right,
      next: next ? status.right - next.left : 0,
    };
  });
  expect(bounds.left).toBeGreaterThanOrEqual(-1);
  expect(bounds.right).toBeLessThanOrEqual(1);
  expect(bounds.next).toBeLessThanOrEqual(1);
  await noOverflow(badge);
}

for (const [device, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  test(`paid pending statuses remain warnings in every admin consumer on ${device}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    // Use the existing demo API and separately mounted admin bundle, as in ui-reuse.spec.ts.
    await page.addInitScript(
      (statuses) => {
        type Row = Record<string, unknown>;
        type Props = { api: (path: string, options?: RequestInit) => Promise<Row> };
        type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
        let bundle: Bundle | undefined;
        const paymentStatuses = new Map<string, string>();
        const records = (value: unknown): Row[] => (Array.isArray(value) ? (value as Row[]) : []);
        function paymentsWithStatuses(value: unknown): Row[] {
          const payments = records(value);
          return payments.map((payment, index) => {
            const status = statuses[index % statuses.length];
            paymentStatuses.set(String(payment.payment_id), status);
            return { ...payment, status };
          });
        }
        Object.defineProperty(window, "SubscriptionWebAppAdmin", {
          configurable: true,
          get: () => bundle,
          set(value: Bundle) {
            const mount = value.mount;
            value.mount = (target, props) =>
              mount(target, {
                ...props,
                api: async (path, options) => {
                  const response = await props.api(path, options);
                  const route = path.split("?")[0];
                  if (route === "/admin/payments") {
                    return { ...response, payments: paymentsWithStatuses(response.payments) };
                  }
                  if (/^\/admin\/payments\/\d+$/.test(route) && response.payment) {
                    const payment = response.payment as Row;
                    return {
                      ...response,
                      payment: {
                        ...payment,
                        status: paymentStatuses.get(String(payment.payment_id)) || statuses[0],
                      },
                    };
                  }
                  if (/^\/admin\/users\/[^/]+$/.test(route) && response.user) {
                    const fixture = await props.api("/admin/payments");
                    return {
                      ...response,
                      recent_payments: paymentsWithStatuses(fixture.payments).slice(0, 2),
                    };
                  }
                  if (/^\/admin\/promos\/\d+\/activations$/.test(route)) {
                    const fixture = await props.api("/admin/payments");
                    const payments = paymentsWithStatuses(fixture.payments).slice(0, 2);
                    return {
                      ...response,
                      total: payments.length,
                      activations: payments.map((payment, index) => ({
                        activation_id: index + 1,
                        promo_id: Number(route.split("/")[3]),
                        user_id: payment.user_id,
                        user_label: payment.user_label,
                        activated_at: payment.created_at,
                        payment_id: payment.payment_id,
                        payment_amount: payment.amount,
                        payment_currency: payment.currency,
                        payment_status: payment.status,
                        payment_provider: payment.provider,
                        payment_sale_mode: payment.sale_mode,
                        payment_description: payment.description,
                        payment_created_at: payment.created_at,
                        effect_summary: "-20%",
                        bonus_days: 0,
                        discount_percent: 20,
                        duration_multiplier: null,
                        traffic_multiplier: null,
                        applies_to: "subscription",
                      })),
                    };
                  }
                  return response;
                },
              });
            bundle = value;
          },
        });
      },
      [...paidStatuses]
    );

    await page.goto(adminUrl("payments"));
    const rows = page.locator(
      device === "desktop" ? ".admin-payments-table tbody tr" : ".admin-payment-mobile-card"
    );
    await expect(rows.nth(1)).toBeVisible();
    await noOverflow(page.locator(".admin-payments-table-shell"));
    for (const [index, status] of paidStatuses.entries()) {
      const row = rows.nth(index);
      const badge = row.locator(".admin-badge");
      await expect(badge).toHaveText(labels[index]);
      await expect(badge).toHaveClass(/admin-badge-warning/);
      await expect(badge).not.toHaveClass(/admin-badge-success|admin-badge-danger/);
      await statusFitsCell(badge);
      await capture(row, `payments-${device}-${status}`, testInfo);
      await row.getByRole("button", { name: /Открыть.*плат/ }).click();
      const dialog = page.locator(".admin-payment-dialog");
      const detailBadge = dialog.locator(".admin-payment-summary-tags .admin-badge").first();
      await expect(detailBadge).toHaveText(labels[index]);
      await expect(detailBadge).toHaveClass(/admin-badge-warning/);
      await expect(detailBadge).not.toHaveClass(/admin-badge-success|admin-badge-danger/);
      const metadataStatus = dialog.locator(".admin-meta-list li").filter({
        has: page.locator("span").filter({ hasText: /^Статус$/ }),
      });
      await expect(metadataStatus.locator("strong")).toHaveText(labels[index]);
      await expect(dialog).not.toContainText(status);
      await statusFitsCell(detailBadge);
      await noOverflow(dialog);
      await capture(dialog, `payment-detail-${device}-${status}`, testInfo);
      await dialog.getByRole("button", { name: "Закрыть", exact: true }).last().click();
    }

    await rows.first().locator(".admin-payments-user-btn").click();
    const user = page.locator(".admin-user-detail-page");
    await user.getByRole("tab", { name: "Платежи", exact: true }).click();
    const recentPayments = user.locator(".admin-user-payments-table tbody tr");
    for (const [index, status] of paidStatuses.entries()) {
      const row = recentPayments.nth(index);
      await expect(row.locator(".admin-badge")).toHaveText(labels[index]);
      await expect(row.locator(".admin-badge")).toHaveClass(/admin-badge-warning/);
      await statusFitsCell(row.locator(".admin-badge"));
      await row.scrollIntoViewIfNeeded();
      await capture(row, `user-payments-${device}-${status}`, testInfo);
    }
    await noOverflow(user);

    await page.goto(adminUrl("promos"));
    await page.getByRole("button", { name: "Редактировать", exact: true }).first().click();
    const promo = page.locator(".admin-promo-edit-dialog");
    await promo.getByRole("tab", { name: "Активации", exact: true }).click();
    const activations = promo.locator(".admin-promo-activations-tab tbody tr");
    for (const [index, status] of paidStatuses.entries()) {
      const row = activations.nth(index);
      await expect(row.locator(".admin-badge")).toHaveText(labels[index]);
      await expect(row.locator(".admin-badge")).toHaveClass(/admin-badge-warning/);
      await statusFitsCell(row.locator(".admin-badge"));
      await row.scrollIntoViewIfNeeded();
      await capture(row, `code-activations-${device}-${status}`, testInfo);
    }
    await noOverflow(promo);
    expect(errors).toEqual([]);
  });

  for (const [index, status] of paidStatuses.entries()) {
    test(`balance top-up shows a neutral ${status} notice on ${device}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize(viewport);
      // Override only the standing demo top-up response; keep the actual API and component.
      await page.route("**/subscription_webapp_docs_demo.js", async (route) => {
        const response = await route.fetch();
        const body = await response.text();
        const topupStatus =
          /(payment_url: `https:\/\/example\.com\/demo-balance-topup[\s\S]*?status: )"pending"/;
        expect(body).toMatch(topupStatus);
        await route.fulfill({
          response,
          body: body.replace(topupStatus, `$1${JSON.stringify(status)}`),
        });
      });
      await page.goto("/demo/runtime/app/?path=/home&mock=user-balance&theme_preview=dark");
      await page.locator('[data-webapp-action="open-balance-topup"]').click();
      const dialog = page.locator(".balance-topup-dialog");
      const submit = dialog.locator(".payment-submit-button");
      await expect(submit).toBeEnabled();
      const checkoutUrl = page.url();
      await submit.click();
      const notice = dialog.getByRole("status");
      await expect(notice).toHaveText(
        index === 0
          ? "Оплата получена; обратитесь в поддержку для проверки."
          : "Оплата получена; покупка применяется."
      );
      await expect(notice).not.toHaveClass(/error/);
      await expect(dialog.locator(".balance-topup-error")).toHaveCount(0);
      await expect(submit).toBeDisabled();
      await expect(page).toHaveURL(checkoutUrl);
      await noOverflow(dialog);
      await capture(dialog, `balance-topup-${device}-${status}`, testInfo);
    });
  }
}
