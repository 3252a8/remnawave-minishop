import { expect, test } from "@playwright/test";

test("conflicting panel edit preserves both versions for comparison", async ({ page }) => {
  await page.addInitScript(() => {
    type Api = (path: string, options?: RequestInit) => Promise<unknown>;
    type Bundle = { mount: (target: HTMLElement, props: { api: Api }) => unknown };
    let bundle: Bundle | undefined;
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: Bundle) {
        let concurrentChange = true;
        const mount = value.mount;
        value.mount = (target, props) =>
          mount(target, {
            ...props,
            api: async (path, options) => {
              if (concurrentChange && path.endsWith("/note") && options?.method === "PUT") {
                concurrentChange = false;
                await props.api(path, {
                  method: "PUT",
                  body: JSON.stringify({
                    note: "Запись другого администратора",
                    previous_note: "",
                  }),
                });
              }
              return props.api(path, options);
            },
          });
        bundle = value;
      },
    });
  });
  await page.goto("/demo/runtime/admin/users/ms_100000000000400080000000000de2b2");
  const card = page.locator(".admin-user-detail-page");
  await card.getByRole("tab", { name: "Заметка", exact: true }).click();
  const panel = card.getByRole("tabpanel", { name: "Заметка" });
  const field = panel.getByRole("textbox", { name: /Заметка в Remnawave/ });
  await field.fill("Мой черновик");
  await panel.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(field).toHaveValue("Мой черновик");
  await expect(panel.getByRole("textbox", { name: "Последняя версия в панели" })).toHaveValue(
    "Запись другого администратора"
  );
  await panel.getByRole("button", { name: "Сохранить мою версию", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("Заметка сохранена в Remnawave.");
  await panel.getByRole("button", { name: "Обновить" }).click();
  await expect(field).toHaveValue("Мой черновик");
});

for (const width of [1440, 390]) {
  test(`admin saves and clears a panel note at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      "/demo/runtime/admin/users/ms_100000000000400080000000000de2b2?theme_preview=dark"
    );
    const card = page.locator(".admin-user-detail-page");
    const tab = card.getByRole("tab", { name: "Заметка", exact: true });
    await tab.click();
    const panel = card.getByRole("tabpanel", { name: "Заметка" });
    const field = panel.getByRole("textbox", { name: /Заметка в Remnawave/ });
    const save = panel.getByRole("button", { name: "Сохранить", exact: true });
    await expect(field).toBeEnabled();
    await expect(save).toBeDisabled();
    await field.fill("Проверить обновление клиента\nпосле пятницы");
    await card.getByRole("tab", { name: "Платежи", exact: true }).click();
    await tab.click();
    await expect(field).toHaveValue("Проверить обновление клиента\nпосле пятницы");
    await save.click();
    await expect(panel.getByRole("status")).toHaveText("Заметка сохранена в Remnawave.");
    await panel.getByRole("button", { name: "Обновить" }).click();
    await expect(field).toHaveValue("Проверить обновление клиента\nпосле пятницы");
    await field.fill("");
    await save.click();
    await expect(panel.getByRole("status")).toHaveText("Заметка сохранена в Remnawave.");
    await expect(save).toBeDisabled();
  });
}
