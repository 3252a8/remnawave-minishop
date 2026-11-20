import { expect, test } from "@playwright/test";

test("the partner list keeps the same columns from loading to loaded", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const url = "/demo/runtime/admin/partners/partners?partner_admin_scenario=";
  const table = page.locator(".partners-list-view table");
  const headers = () =>
    table.locator("thead th").evaluateAll((cells) =>
      cells.map((cell) => ({
        label: cell.textContent?.trim(),
        width: Math.round(cell.getBoundingClientRect().width),
      }))
    );

  await page.goto(url + "loading");
  await expect(table).toHaveClass(/admin-table-skeleton/);
  const loadingHeaders = await headers();

  await page.goto(url + "populated");
  await expect(table.getByRole("columnheader", { name: "Действия" })).toBeVisible();
  await expect(table.locator("tbody tr").first()).toBeVisible();
  expect(await headers()).toEqual(loadingHeaders);
});
