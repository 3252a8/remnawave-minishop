import { expect, test } from "@playwright/test";

const dashboard = "/demo/runtime/admin/stats";
const updater = `${dashboard}/updater`;

for (const width of [390, 1440]) {
  test(`an administrator connects an offline updater at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
    await page.addInitScript(() => localStorage.setItem("rw_minishop_demo_language", "en"));
    await page.goto("/demo/runtime/admin/stats?theme_preview=dark&mock=core-update-offline");
    await page.getByRole("button", { name: "Update Minishop", exact: true }).click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByText("The update service is offline", { exact: true })).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Copy command" })).toBeVisible();
    await expect(dialog.locator("pre").first()).toContainText(
      "/-/raw/7a51b934/deploy/docker/install-updater.sh"
    );
    await expect(dialog.getByRole("link", { name: "Installer script on GitLab" })).toHaveAttribute(
      "href",
      /\/-\/blob\/7a51b934\/deploy\/docker\/install-updater\.sh$/
    );
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

  test(`the up-to-date dashboard opens the installer by URL at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.addInitScript(() => localStorage.setItem("rw_minishop_demo_language", "en"));
    const query = "?theme_preview=light&mock=core-update-current";
    await page.goto(dashboard + query);
    const check = page.getByRole("button", { name: "Check for updates" });
    await expect(check.locator("..").getByRole("button", { name: "Synchronize" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Minishop updates" })).toHaveCount(0);
    await check.click();
    const dialog = page.getByRole("dialog", { name: "Minishop updates" });
    await expect(page).toHaveURL(updater + query);
    await expect(
      dialog.getByRole("status").filter({ hasText: "This tag is up to date." })
    ).toBeVisible();
    await page.goBack();
    await expect(dialog).toHaveCount(0);
    await expect(check).toBeFocused();
    await page.goForward();
    await expect(dialog).toBeVisible();
    await page.reload();
    await expect(dialog.getByText("This tag is up to date.")).toBeVisible();
    await expect(dialog.getByRole("link", { name: "Installer script on GitLab" })).toHaveAttribute(
      "href",
      /\/-\/blob\/dev\/deploy\/docker\/install-updater\.sh$/
    );
    const code = dialog.locator("pre code").first();
    await expect(code).toBeVisible();
    const command = await code.textContent();
    expect(command).toContain("/-/raw/dev/deploy/docker/install-updater.sh");
    expect(command).not.toContain("\n");
    await dialog.getByRole("button", { name: "Copy command" }).click();
    await expect(dialog.getByText("Command copied.")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(command);
    expect(await dialog.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
    await page.keyboard.press("Escape");
    await expect(page).toHaveURL(dashboard + query);
    await expect(dialog).toHaveCount(0);
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
