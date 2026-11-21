import { expect, test } from "@playwright/test";

for (const width of [390, 1440]) {
  test(`an administrator connects an offline updater at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.addInitScript(() => localStorage.setItem("rw_minishop_demo_language", "en"));
    await page.goto("/demo/runtime/admin/stats?theme_preview=dark&mock=core-update-offline");
    await page.getByRole("button", { name: "Update Minishop", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("The update service is offline", { exact: true })).toBeVisible();
    await dialog.getByText("How to connect the service", { exact: true }).click();
    await expect(dialog.locator("pre").first()).toContainText("--enroll /opt/remnawave-minishop");
    await expect(
      dialog.getByRole("link", { name: "Service files for this build" })
    ).toHaveAttribute("href", /\/archive\/7a51b934\//);
    await expect(
      dialog.getByRole("link", { name: "Compatibility and troubleshooting" })
    ).toHaveAttribute("href", /\/troubleshooting\/maintenance\/#/);
    const recheck = dialog.getByRole("button", { name: "Check connection" });
    await recheck.click();
    await expect(dialog.getByText(/No response yet/)).toBeVisible();
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.evaluate(() => {
      const current = new URL(location.href);
      current.searchParams.set("mock", "core-update");
      history.replaceState(null, "", current);
    });
    await recheck.click();
    await expect(dialog.getByRole("button", { name: "Start update" })).toBeEnabled();
    await expect(dialog.getByText("Update queued", { exact: true })).toHaveCount(0);
  });

  test(`an administrator previews a tag before updating at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.addInitScript(() => localStorage.setItem("rw_minishop_demo_language", "en"));
    await page.goto("/demo/runtime/admin/stats?theme_preview=dark&mock=core-update");
    await page.getByRole("button", { name: "Update Minishop", exact: true }).click();
    const dialog = page.getByRole("dialog");
    const start = dialog.getByRole("button", { name: "Start update" });
    const field = dialog.getByRole("textbox", { name: "Image tag (IMAGE_TAG)" });
    await field.fill("dev");
    await expect(start).toBeDisabled();
    await dialog.getByRole("button", { name: "Check", exact: true }).click();
    await expect(start).toBeEnabled();
    const notify = dialog.getByRole("switch");
    await notify.click();
    await expect(notify).toHaveAttribute("aria-checked", "false");
    await start.click();
    await expect(dialog.getByText("Update queued", { exact: true })).toBeVisible();
    await dialog.getByRole("button", { name: "Close", exact: true }).last().click();
    await page.getByRole("button", { name: "View progress" }).click();
    await expect(dialog.getByText("Update complete", { exact: true })).toBeVisible({
      timeout: 25_000,
    });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width
    );
  });
}
