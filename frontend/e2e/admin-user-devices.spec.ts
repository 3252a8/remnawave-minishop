import { expect, test, type Page } from "@playwright/test";

async function seedSortCases(page: Page) {
  await page.addInitScript(() => {
    type Api = (path: string, options?: RequestInit) => Promise<unknown>;
    type Bundle = { mount: (target: HTMLElement, props: { api: Api }) => unknown };
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
              const result = await props.api(path, options);
              if (!path.endsWith("/hwid-devices")) return result;
              const { devices } = result as { devices: Record<string, unknown>[] };
              return {
                ok: true,
                devices: [
                  ["Phone 10", "iOS", "happ/10", "2030-01-03T10:00:00+09:00"],
                  ["Tablet", "", "", "invalid"],
                  ["Phone 2", "Android", "Happ/2", "2030-01-03T09:00:00Z"],
                  ["Router", "", "", null],
                ].map(([display_name, platform_label, user_agent, last_connected_at], index) => ({
                  ...devices[0],
                  index,
                  display_name,
                  platform_label,
                  user_agent,
                  last_connected_at,
                })),
              };
            },
          });
        bundle = value;
      },
    });
  });
}

for (const width of [1440, 390]) {
  test(`admin sorts device rows at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await seedSortCases(page);
    await page.goto("/demo/runtime/admin/users/ms_100000000000400080000000000de2b2");
    await page.getByRole("tab", { name: "Устройства", exact: true }).click();
    const panel = page.getByRole("tabpanel", { name: "Устройства" });
    const names = panel.locator("tbody tr strong");
    const original = ["Phone 10", "Tablet", "Phone 2", "Router"];
    const knownFirst = ["Phone 2", "Phone 10", "Tablet", "Router"];
    const knownReversed = ["Phone 10", "Phone 2", "Tablet", "Router"];
    await expect(names).toHaveText(original);
    await expect(panel.locator('td[data-label="Последнее подключение"]').nth(1)).toHaveText("—");

    const mobileSort = panel.getByRole("combobox", { name: "Сортировка" });
    const selectOption = async (label: string) => {
      await mobileSort.click();
      await page.getByRole("option", { name: label, exact: true }).click();
    };
    for (const [label, ascending, descending] of [
      [
        "Устройство",
        ["Phone 2", "Phone 10", "Router", "Tablet"],
        ["Tablet", "Router", "Phone 10", "Phone 2"],
      ],
      ["Платформа", knownFirst, knownReversed],
      ["Приложение подключения", knownFirst, knownReversed],
      ["Последнее подключение", knownReversed, knownFirst],
    ] as const) {
      const date = label === "Последнее подключение";
      const firstOrder = date ? descending : ascending;
      const nextOrder = date ? ascending : descending;
      if (width === 390) {
        await selectOption(`${label} · ${date ? "Сначала новые" : "от А до Я"}`);
        await expect(names).toHaveText([...firstOrder]);
        await selectOption(`${label} · ${date ? "Сначала старые" : "от Я до А"}`);
      } else {
        const header = panel.getByRole("columnheader", { name: label, exact: true });
        const button = header.getByRole("button");
        await button.focus();
        await button.press("Enter");
        await expect(header).toHaveAttribute("aria-sort", date ? "descending" : "ascending");
        await expect(names).toHaveText([...firstOrder]);
        await button.press("Enter");
        await expect(header).toHaveAttribute("aria-sort", date ? "ascending" : "descending");
      }
      await expect(names).toHaveText([...nextOrder]);
    }
    if (width === 390) await selectOption("Без сортировки");
    else
      await panel
        .getByRole("button", { name: "Последнее подключение", exact: true })
        .press("Enter");
    await expect(names).toHaveText(original);
  });

  test(`admin removes one selected device at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      "/demo/runtime/admin/users/ms_100000000000400080000000000de2b2?theme_preview=dark"
    );
    const card = page.locator(".admin-user-detail-page");
    const usage = card.getByRole("button", { name: /^Открыть устройства,/ });
    if (width === 390) await usage.click();
    else {
      await usage.focus();
      await usage.press("Enter");
    }
    const tab = card.getByRole("tab", { name: "Устройства", exact: true });
    await expect(tab).toHaveAttribute("aria-selected", "true");
    await expect(tab).toBeFocused();
    await expect(tab).toBeInViewport();
    const panel = card.getByRole("tabpanel", { name: "Устройства" });
    const rows = panel.locator("tbody tr");
    await expect(rows.nth(1)).toBeVisible();
    const apps = panel.locator('td[data-label="Приложение подключения"]');
    await expect(apps.nth(0)).toHaveText("Streisand 1.6");
    await expect(apps.nth(1)).toHaveText("Happ 3.1.0");
    const total = await rows.count();
    const first = await rows.first().locator("strong").innerText();
    const second = await rows.nth(1).locator("strong").innerText();
    const remove = rows.first().getByRole("button", { name: `Удалить ${first}` });
    await remove.click();
    const dialog = page.getByRole("dialog", { name: "Удалить устройство?" });
    await expect(dialog).toContainText(first);
    await dialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(remove).toBeFocused();
    await expect(rows).toHaveCount(total);
    await remove.click();
    await dialog.getByRole("button", { name: "Удалить", exact: true }).click();
    await expect(dialog).toBeHidden();
    await expect(rows).toHaveCount(total - 1);
    await panel.getByRole("button", { name: "Обновить" }).click();
    await expect(rows.first().locator("strong")).toHaveText(second);
    await expect(
      card.locator(".admin-user-stat").filter({ hasText: "HWID-устройства" })
    ).toContainText(`${total - 1} / 6`);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
  });
}
