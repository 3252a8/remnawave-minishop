import { expect, test } from "@playwright/test";

test("plugin library and import dialog work at desktop and mobile sizes", async ({
  page,
}, testInfo) => {
  await page.addInitScript(() => {
    type Api = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
    type AdminBundle = {
      mount: (target: HTMLElement, props: { api: Api } & Record<string, unknown>) => unknown;
    };
    let bundle: AdminBundle | undefined;
    let enabled = true;
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: AdminBundle) {
        const mount = value.mount;
        value.mount = (target, props) =>
          mount(target, {
            ...props,
            api: async (path, options) => {
              if (path === "/admin/plugins")
                return {
                  ok: true,
                  generation: enabled ? 2 : 3,
                  installations: {
                    pro: {
                      digest: "a".repeat(64),
                      version: "0.1.24",
                      publisher: "Example publisher",
                      enabled,
                      status: "active",
                      source: { kind: "image" },
                    },
                  },
                  bundled: [],
                  operations: [
                    { id: "op-1", action: "install", plugin: "pro", status: "completed" },
                  ],
                  observations: { backend: { generation: 2, status: "active" } },
                };
              if (path === "/admin/plugins/pro/enabled") {
                enabled = Boolean(JSON.parse(String(options?.body || "{}"))?.enabled);
                return { ok: true };
              }
              return props.api(path, options);
            },
          });
        bundle = value;
      },
    });
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/demo/runtime/admin/plugins");
  const card = page.locator('[data-plugin-id="pro"]');
  await expect(card).toBeVisible();
  await expect(card.getByRole("switch")).toBeChecked();
  await page.screenshot({
    path: testInfo.outputPath("plugin-manager-desktop.png"),
    fullPage: true,
  });

  await card.getByRole("switch").click();
  await expect(card.getByRole("switch")).not.toBeChecked();
  await page.getByRole("button", { name: "Добавить плагин" }).first().click();
  const dialog = page.locator(".plugin-import-dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Перетащите ZIP плагина")).toBeVisible();
  await dialog.getByRole("button", { name: "Git-репозиторий" }).click();
  await expect(dialog.getByPlaceholder("https://github.com/author/repository")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Git-репозиторий" })).toHaveAttribute(
    "aria-pressed",
    "true"
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(dialog).toBeVisible();
  const noHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth + 1
  );
  expect(noHorizontalOverflow).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("plugin-manager-mobile.png"), fullPage: true });
});
