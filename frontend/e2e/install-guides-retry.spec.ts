import { expect, test } from "@playwright/test";

for (const width of [1280, 390]) {
  test(`public install instructions recover after a preload error (${width}px)`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const token = "a".repeat(32);
    await page.addInitScript((token) => {
      Object.assign(window, {
        __RW_PUBLIC_INSTALL_PRELOAD__: {
          path: `/subscription-guides/public/${token}`,
          promise: Promise.resolve({
            ok: true,
            enabled: false,
            config: null,
            error: "Panel service is unavailable",
          }),
        },
      });
    }, token);
    await page.goto(`/s/${token}`);
    const shell = page.locator(".public-install-shell");
    await expect(shell.getByText("Инструкции недоступны.", { exact: true })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("unavailable.png"), fullPage: true });
    await shell.getByRole("button", { name: "Загрузить снова", exact: true }).click();
    await expect(shell.locator(".install-empty")).toHaveCount(0);
    await expect(
      shell.getByRole("button", { name: "Добавить подписку", exact: true })
    ).toBeVisible();
    await expect(shell.locator(".install-step-motion").last()).toHaveCSS("opacity", "1");
    await expect(page).toHaveURL(new RegExp(`/s/${token}$`));
    await page.screenshot({ path: testInfo.outputPath("recovered.png"), fullPage: true });
  });
}
