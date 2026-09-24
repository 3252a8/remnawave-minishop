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
                      name: "Example plugin",
                      description: "Example plugin description",
                      publisher: "Example publisher",
                      enabled,
                      status: "active",
                      source: { kind: "image" },
                    },
                  },
                  bundled: [{ id: "pro", source: "image", status: "active" }],
                  operations: [
                    { id: "op-1", action: "install", plugin: "pro", status: "completed" },
                  ],
                  observations: { backend: { generation: 2, status: "active" } },
                };
              if (path === "/admin/plugins/pro/enabled") {
                enabled = Boolean(JSON.parse(String(options?.body || "{}"))?.enabled);
                return { ok: true };
              }
              if (path === "/admin/plugins/updates") return { ok: true, updates: {} };
              if (path === "/admin/plugins/runtime") return { ok: true, plugins: [] };
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
  await expect(card).toHaveCount(1);
  await expect(page.locator(".admin-list-toolbar-summary strong")).toHaveText("1");
  await card.getByRole("button", { name: /0\.1\.24/ }).click();
  await expect(page.locator(".plugin-package-dialog")).toBeVisible();
  await expect(page.locator(".plugin-package-dialog").getByText("Образ приложения")).toBeVisible();
  await page.locator(".plugin-package-dialog").getByRole("button", { name: "Закрыть" }).click();
  await expect(page.locator(".plugin-package-dialog")).not.toBeVisible();
  await expect(card.getByRole("switch")).toBeChecked();
  await page.screenshot({
    path: testInfo.outputPath("plugin-manager-desktop.png"),
    fullPage: true,
  });

  await card.getByRole("switch").click();
  await expect(card.getByRole("switch")).not.toBeChecked();
  await card.getByRole("button", { name: "Настройки" }).click();
  await expect(page.getByText("У этого плагина пока нет настроек.")).toBeVisible();
  await page.getByRole("button", { name: "Все плагины" }).click();
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

test("an enabled package is removed with one request and visible restart progress", async ({
  page,
}) => {
  await page.addInitScript(() => {
    type Api = (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
    type AdminBundle = {
      mount: (target: HTMLElement, props: { api: Api } & Record<string, unknown>) => unknown;
    };
    let bundle: AdminBundle | undefined;
    let installed = true;
    let inventoryReads = 0;
    let removeCalls = 0;
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: AdminBundle) {
        const mount = value.mount;
        value.mount = (target, props) =>
          mount(target, {
            ...props,
            api: async (path, options) => {
              if (path === "/admin/plugins") {
                inventoryReads += 1;
                const ready = installed || inventoryReads > 2;
                return {
                  ok: true,
                  generation: installed ? 2 : 3,
                  installations: installed
                    ? {
                        "sample-plugin": {
                          digest: "a".repeat(64),
                          version: "1.0.0",
                          name: "Sample plugin",
                          publisher: "Example publisher",
                          enabled: true,
                          status: "active",
                          source: { kind: "archive" },
                        },
                      }
                    : {},
                  bundled: [],
                  observations: {
                    backend: {
                      generation: installed ? 2 : 3,
                      status: ready ? "active" : "starting",
                    },
                    worker: {
                      generation: installed ? 2 : 3,
                      status: ready ? "active" : "starting",
                    },
                  },
                };
              }
              if (path === "/admin/plugins/sample-plugin/remove") {
                removeCalls += 1;
                installed = false;
                // The supervisor can stop the backend before its response reaches the browser.
                throw new Error("connection closed during restart");
              }
              if (path === "/admin/plugins/updates") return { ok: true, updates: {} };
              if (path === "/admin/plugins/runtime") return { ok: true, plugins: [] };
              return props.api(path, options);
            },
          });
        bundle = value;
        Object.defineProperty(window, "pluginRemoveCalls", { get: () => removeCalls });
      },
    });
  });

  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/demo/runtime/admin/plugins");
  await page
    .locator('[data-plugin-id="sample-plugin"]')
    .getByRole("button", { name: "Настройки" })
    .click();
  await page.getByRole("tab", { name: "Обновления" }).click();
  const actions = page.locator(".plugin-update-actions");
  const add = actions.getByRole("button", { name: "Добавить плагин" });
  const remove = actions.getByRole("button", { name: "Удалить пакет" });
  await expect(remove).toHaveClass(/admin-btn-danger/);
  const addBox = await add.boundingBox();
  const removeBox = await remove.boundingBox();
  expect(addBox && removeBox && Math.abs(addBox.y - removeBox.y)).toBeLessThan(1);
  await remove.click();
  const dialog = page.locator(".plugin-remove-dialog");
  await expect(dialog.getByText("Перезапустить сервер и фоновый процесс")).toBeVisible();
  await dialog.getByRole("button", { name: "Удалить пакет" }).click();
  await expect(dialog.getByText("Плагин удалён. Приложение готово к работе.")).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { pluginRemoveCalls: number }).pluginRemoveCalls
    )
  ).toBe(1);
  await dialog.getByRole("button", { name: "Закрыть" }).last().click();
  await expect(page.locator('[data-plugin-id="sample-plugin"]')).toHaveCount(0);
});
