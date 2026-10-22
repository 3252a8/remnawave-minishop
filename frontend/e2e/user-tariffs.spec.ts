import { expect, test, type Page } from "@playwright/test";
import type { ActiveTariff } from "../src/lib/admin/subscriptionPlans";

async function useTariffStats(page: Page, rows: ActiveTariff[]) {
  await page.addInitScript((rows) => {
    type Row = Record<string, unknown>;
    type Props = { api: (path: string, options?: RequestInit) => Promise<Row> };
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
              const response = await props.api(path, options);
              return path.split("?")[0] === "/admin/stats"
                ? { ...response, active_tariffs: rows }
                : response;
            },
          });
        bundle = value;
      },
    });
  }, rows);
}

const smallDistribution: ActiveTariff[] = [
  {
    kind: "tariff",
    tariff_key: "tnnl",
    tariff_names: { ru: "TNNL", en: "TNNL" },
    is_configured: true,
    is_enabled: true,
    active_users: 223,
  },
  ...(["trial", "unassigned"] as const).map((kind) => ({
    kind,
    tariff_key: null,
    tariff_names: {},
    is_configured: false,
    is_enabled: null,
    active_users: 0,
  })),
];

for (const width of [1440, 768, 390, 320]) {
  test(`small tariff distribution stays compact without disclosure at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await useTariffStats(page, smallDistribution);
    await page.goto("/demo/runtime/admin/stats?theme_preview=dark");
    const card = page.locator(".admin-stats-tariffs");
    const rows = card.locator(".admin-tariff-distribution-row");
    await expect(rows).toHaveCount(3);
    await expect(card.locator(".admin-tariff-distribution-toggle")).toHaveCount(0);
    await expect(rows.first()).toContainText("223");
    await expect(rows.first()).toContainText("100");
    const boxes = await rows.evaluateAll((rows) =>
      rows.map((row) => {
        const { top, width, height } = row.getBoundingClientRect();
        return { top, width, height };
      })
    );
    expect(boxes.every((box) => box.height >= 44)).toBe(true);
    if (width >= 768) {
      expect(new Set(boxes.map((box) => box.top)).size).toBe(1);
      expect(boxes.every((box) => box.width < 400)).toBe(true);
    } else {
      expect(new Set(boxes.map((box) => box.top)).size).toBe(3);
    }
    await card.screenshot({ path: testInfo.outputPath(`tariffs-${width}.png`) });
    await page.locator('[data-admin-tariff-filter="trial"]').click();
    await expect(page).toHaveURL(/users_tariff=trial/);
  });
}

for (const width of [1440, 390]) {
  test(`large tariff distribution wraps names and expands at ${width}px`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const longName = "PlanWithAVeryLongUnbrokenName".repeat(3);
    await useTariffStats(
      page,
      Array.from({ length: 9 }, (_, index) => ({
        ...smallDistribution[0],
        tariff_key: `plan-${index}-${"long-key".repeat(8)}`,
        tariff_names: { en: index < 2 ? longName : `Plan ${index}` },
        active_users: 9 - index,
        is_enabled: index !== 0,
        is_configured: index !== 1,
      }))
    );
    await page.goto("/demo/runtime/admin/stats?theme_preview=light");
    const card = page.locator(".admin-stats-tariffs");
    const rows = card.locator(".admin-tariff-distribution-row");
    const toggle = card.locator(".admin-tariff-distribution-toggle");
    await expect(rows).toHaveCount(6);
    await expect(rows.first()).toContainText(longName);
    await expect(toggle).toContainText("+3");
    await toggle.click();
    await expect(rows).toHaveCount(9);
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(await card.evaluate((card) => card.scrollWidth - card.clientWidth)).toBeLessThanOrEqual(
      2
    );
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      )
    ).toBeLessThanOrEqual(2);
    await card.screenshot({ path: testInfo.outputPath(`tariffs-expanded-${width}.png`) });
    await toggle.click();
    await expect(rows).toHaveCount(6);
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
  });
}

for (const width of [1440, 390]) {
  test(`tariff dashboard drilldown and trial filter persist at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/demo/runtime/admin/stats?theme_preview=dark");
    const row = page.locator('[data-admin-tariff-filter="tariff:standard"]');
    await expect(row).toBeVisible();
    const warning = page.locator(".admin-config-alerts");
    await expect(warning).toBeVisible();
    await expect
      .poll(() =>
        warning.evaluate((alert) => {
          const card = alert.parentElement?.querySelector(".admin-stats-audience-card");
          if (!alert.getClientRects().length || !card?.getClientRects().length) return -1;
          const alertBox = alert.getBoundingClientRect();
          return card.getBoundingClientRect().top - alertBox.bottom;
        })
      )
      .toBeGreaterThanOrEqual(15);
    const count = Number(
      await row.locator(".admin-tariff-distribution-number strong").textContent()
    );
    await row.click();
    await expect(page).toHaveURL(/users_filter=active_subscription/);
    await expect(page).toHaveURL(/users_tariff=tariff%3Astandard/);
    await expect(page.locator(".admin-list-toolbar-summary strong")).toHaveText(String(count));
    await page.reload();
    await expect(page.locator(".admin-list-toolbar-summary strong")).toHaveText(String(count));
    const tariffSelect = page.locator('.admin-select-trigger[aria-label="Тариф / триал"]');
    if (width < 720) await page.locator(".admin-users-filter-toggle").click();
    await tariffSelect.filter({ visible: true }).click();
    await page.getByRole("option", { name: "Триал", exact: true }).click();
    await expect(page).toHaveURL(/users_tariff=trial/);
    if (width < 720) {
      const dialog = page.locator(".admin-users-filter-dialog");
      await expect(dialog).toBeVisible();
      await dialog.getByRole("button", { name: "Готово", exact: true }).click();
    }
    const plans = page.locator(
      width < 720
        ? ".admin-users-mobile-list .admin-subscription-plan"
        : ".admin-users-cell-tariff .admin-subscription-plan"
    );
    await expect(plans.first()).toHaveText("Триал");
    await expect(page.locator(".admin-users-filter-chips")).toContainText("Триал");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(2);
    expect(errors).toEqual([]);
  });
}
