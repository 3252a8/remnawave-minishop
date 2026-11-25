import { expect, test } from "@playwright/test";

const userPath = "/demo/runtime/admin/users/ms_100000000000400080000000000de2b2";
test.use({ timezoneId: "UTC" });

for (const width of [1440, 390]) {
  test(`admin suspends and resumes the current subscription at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.clock.setFixedTime(new Date("2030-01-03T12:00:00Z"));
    await page.goto(`${userPath}?theme_preview=${width === 390 ? "dark" : "light"}`);
    const actions = page.getByRole("tab", { name: "Действия", exact: true });
    const subscription = page.getByRole("tab", { name: "Подписка", exact: true });
    const currentEnd = page
      .locator(".admin-user-subscription-facts li")
      .filter({ hasText: "Активна до" });
    await subscription.click();
    await expect(currentEnd).toContainText("22.11.2035");
    await actions.click();
    const zone = page.locator(".admin-danger-zone");
    const suspend = zone.getByRole("button", { name: "Приостановить подписку", exact: true });
    const resume = zone.getByRole("button", { name: "Возобновить подписку", exact: true });
    const dialog = page.getByRole("dialog");
    await suspend.click();
    await expect(dialog).toContainText("№520002");
    await expect(dialog).toContainText("обращаться в поддержку");
    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
    await expect(suspend).toBeFocused();
    await suspend.press("Enter");
    await dialog.screenshot({ path: testInfo.outputPath(`suspension-dialog-${width}.png`) });
    await dialog.getByRole("button", { name: "Приостановить подписку" }).click();
    await expect(dialog).toBeHidden();
    await expect(resume).toBeEnabled();
    await expect(zone).toContainText("Подписка приостановлена с 03.01.2030");
    await expect(zone.getByRole("button", { name: "Заблокировать", exact: true })).toBeVisible();
    await zone.screenshot({ path: testInfo.outputPath(`suspended-actions-${width}.png`) });
    await subscription.click();
    await expect(
      page.locator(".admin-mini-list-row").filter({ hasText: "Подписка приостановлена" })
    ).toHaveCount(1);
    await page.clock.setFixedTime(new Date("2030-01-05T12:00:00Z"));
    await actions.click();
    await resume.click();
    await expect(dialog).toContainText("на фактическое время приостановки");
    await dialog.getByRole("button", { name: "Возобновить подписку" }).click();
    await expect(dialog).toBeHidden();
    await expect(suspend).toBeEnabled();
    await subscription.click();
    await expect(currentEnd).toContainText("24.11.2035");
  });
}

test("admin can retry a suspension left pending after a panel error", async ({ page }) => {
  await page.addInitScript(() => {
    type Response = Record<string, unknown> & { active_subscription?: Record<string, unknown> };
    type Props = { api: (path: string, options?: RequestInit) => Promise<Response> };
    type Bundle = { mount: (target: HTMLElement, props: Props) => unknown };
    let panelFailed = false;
    let bundle: Bundle;
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: Bundle) {
        const mount = value.mount;
        value.mount = (target, props) =>
          mount(target, {
            ...props,
            api: async (path, options) => {
              if (path.endsWith("/subscription-suspension")) {
                if (!panelFailed) {
                  panelFailed = true;
                  return { ok: false, error: "panel_status_update_failed" };
                }
                panelFailed = false;
              }
              const response = await props.api(path, options);
              if (panelFailed && response.active_subscription) {
                return {
                  ...response,
                  suspended_subscription: {
                    ...response.active_subscription,
                    is_active: true,
                    suspended_at: "2030-01-03T12:00:00Z",
                  },
                };
              }
              return response;
            },
          });
        bundle = value;
      },
    });
  });
  await page.goto(userPath);
  await page.getByRole("tab", { name: "Действия", exact: true }).click();
  const zone = page.locator(".admin-danger-zone");
  const dialog = page.getByRole("dialog");
  await zone.getByRole("button", { name: "Приостановить подписку" }).click();
  await dialog.getByRole("button", { name: "Приостановить подписку" }).click();
  await expect(dialog.getByRole("alert")).toBeVisible();
  await dialog.getByRole("button", { name: "Отмена" }).click();
  await expect(zone).toContainText("Ожидается подтверждение панели.");
  await zone.getByRole("button", { name: "Повторить приостановку" }).click();
  await dialog.getByRole("button", { name: "Приостановить подписку" }).click();
  await expect(zone.getByRole("button", { name: "Возобновить подписку" })).toBeEnabled();
});
