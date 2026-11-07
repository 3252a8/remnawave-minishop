import { expect, test, type Page } from "@playwright/test";

const USER_PATH = "/demo/runtime/admin/users/ms_100000000000400080000000000de2b2";
const REQUESTS_KEY = "minishop.test.adminHwidResetRequests";

async function observeResetRequests(page: Page) {
  await page.addInitScript((key) => {
    type ApiResult = Record<string, unknown>;
    type Props = { api: (path: string, options?: RequestInit) => Promise<ApiResult> };
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
              if (path.endsWith("/hwid-devices/reset")) {
                const requests = JSON.parse(sessionStorage.getItem(key) || "[]");
                requests.push({ path, method: options?.method });
                sessionStorage.setItem(key, JSON.stringify(requests));
              }
              return props.api(path, options);
            },
          });
        bundle = value;
      },
    });
  }, REQUESTS_KEY);
}

async function resetRequests(page: Page): Promise<{ path: string; method: string }[]> {
  return page.evaluate((key) => JSON.parse(sessionStorage.getItem(key) || "[]"), REQUESTS_KEY);
}

for (const width of [1440, 390]) {
  test(`admin clears recorded HWIDs without changing subscription at ${width}px`, async ({
    page,
  }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await observeResetRequests(page);
    await page.goto(`${USER_PATH}?theme_preview=dark`);

    const card = page.locator(".admin-user-detail-page");
    const usage = card
      .locator(".admin-user-stat")
      .filter({ hasText: "HWID-устройства" })
      .locator("strong");
    await expect(usage).toHaveText(/^[1-9]\d* \/ 6$/);
    const originalUsage = await usage.innerText();
    const subscriptionLink = card.locator('a[href^="https://connect.demo.example/sub/"]');
    await expect(subscriptionLink).toHaveCount(1);
    const originalLink = await subscriptionLink.getAttribute("href");

    await card.getByRole("tab", { name: "Действия", exact: true }).click();
    const limit = card.getByRole("spinbutton", { name: "Лимит устройств", exact: true });
    await expect(limit).toHaveValue("4");
    const reset = card.locator('[data-admin-action="reset-user-hwid-devices"]');
    await expect(reset).toBeEnabled();
    await reset.click();
    const dialog = page.locator(".admin-user-hwid-reset-dialog");
    await expect(dialog).toBeVisible();
    const confirm = dialog.locator('[data-admin-action="confirm-user-hwid-reset"]');
    await expect(confirm).toBeInViewport();
    expect(
      await dialog.evaluate((element) => element.scrollWidth - element.clientWidth)
    ).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: testInfo.outputPath(`admin-hwid-reset-confirm-${width}.png`),
      fullPage: true,
    });

    await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(usage).toHaveText(originalUsage);
    expect(await resetRequests(page)).toEqual([]);

    await reset.click();
    await confirm.click();
    await expect(dialog).toBeHidden();
    await expect(usage).toHaveText("0 / 6");
    await expect(limit).toHaveValue("4");
    await expect(subscriptionLink).toHaveAttribute("href", originalLink!);
    const requests = await resetRequests(page);
    expect(requests).toHaveLength(1);
    expect(requests[0].method).toBe("POST");
    expect(requests[0].path).toMatch(/^\/admin\/users\/[^/]+\/hwid-devices\/reset$/);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      )
    ).toBeLessThanOrEqual(2);
    await page.screenshot({
      path: testInfo.outputPath(`admin-hwid-reset-result-${width}.png`),
      fullPage: true,
    });
    expect(errors).toEqual([]);
  });
}
