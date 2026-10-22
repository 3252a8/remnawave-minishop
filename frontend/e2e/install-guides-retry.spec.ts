import { expect, test } from "@playwright/test";

for (const width of [1280, 390]) {
  for (const publicMode of [false, true]) {
    test(`install destinations select stable app IDs and follow history (${publicMode ? "public" : "account"}, ${width}px)`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 900 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const path = publicMode
        ? `/s/${"b".repeat(32)}?`
        : "/demo/runtime/app/?mock=checkout-addons&path=/install&";
      await page.goto(`${path}platform=android&app=v2rayng`);
      await expect(page.locator(".install-platform-trigger")).toContainText("Android");
      await expect(page.locator(".install-app-button.active")).toContainText("v2rayNG");
      await page.screenshot({ path: testInfo.outputPath("targeted-install.png"), fullPage: true });
      await page.evaluate(() => {
        const url = new URL(window.location.href);
        url.searchParams.set("platform", "ios");
        url.searchParams.delete("app");
        window.history.pushState(null, "", url);
        window.dispatchEvent(new PopStateEvent("popstate"));
      });
      await expect(page.locator(".install-platform-trigger")).toContainText("iOS");
      await expect(page.locator(".install-app-button.active")).toContainText("RabbitHole");
      await page.goBack();
      await expect(page.locator(".install-platform-trigger")).toContainText("Android");
      await expect(page.locator(".install-app-button.active")).toContainText("v2rayNG");
      await page.locator(".install-app-button").filter({ hasText: "Happ" }).click();
      await expect(page.locator(".install-app-button.active")).toContainText("Happ");
      await page.evaluate(() => window.dispatchEvent(new PopStateEvent("popstate")));
      await expect(page.locator(".install-app-button.active")).toContainText("v2rayNG");
      expect(errors).toEqual([]);
    });
  }

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
