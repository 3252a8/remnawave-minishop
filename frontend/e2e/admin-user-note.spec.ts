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
  const panel = card
    .locator(".admin-user-hero")
    .getByRole("region", { name: "Заметка в Remnawave" });
  await panel.getByRole("button", { name: "Добавить заметку" }).click();
  const field = panel.getByRole("textbox", { name: /Заметка в Remnawave/ });
  await field.fill("Мой черновик");
  await panel.getByRole("button", { name: "Сохранить", exact: true }).click();
  await expect(field).toHaveValue("Мой черновик");
  await expect(panel.getByRole("textbox", { name: "Последняя версия в панели" })).toHaveValue(
    "Запись другого администратора"
  );
  await panel.getByRole("button", { name: "Сохранить мою версию", exact: true }).click();
  await expect(panel.getByRole("status")).toHaveText("Заметка сохранена в Remnawave.");
  await panel.getByRole("button", { name: "Обновить заметку" }).click();
  await expect(panel.getByText("Мой черновик", { exact: true })).toBeVisible();
});

for (const width of [1440, 390]) {
  test(`admin saves and clears a panel note at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(
      "/demo/runtime/admin/users/ms_100000000000400080000000000de2b2?theme_preview=dark"
    );
    const card = page.locator(".admin-user-detail-page");
    await expect(card.getByRole("tab", { name: "Заметка", exact: true })).toHaveCount(0);
    const panel = card
      .locator(".admin-user-hero")
      .getByRole("region", { name: "Заметка в Remnawave" });
    const add = panel.getByRole("button", { name: "Добавить заметку" });
    await add.click();
    const field = panel.getByRole("textbox", { name: /Заметка в Remnawave/ });
    const save = panel.getByRole("button", { name: "Сохранить", exact: true });
    await expect(field).toBeEnabled();
    await expect(save).toBeDisabled();
    await field.fill("Проверить обновление клиента\nпосле пятницы");
    await card.getByRole("tab", { name: "Платежи", exact: true }).click();
    await expect(field).toHaveValue("Проверить обновление клиента\nпосле пятницы");
    await save.click();
    await expect(panel.getByRole("status")).toHaveText("Заметка сохранена в Remnawave.");
    await panel.getByRole("button", { name: "Обновить заметку" }).click();
    await expect(panel.getByText("Проверить обновление клиента после пятницы")).toBeVisible();
    await panel.getByRole("button", { name: "Редактировать" }).click();
    await expect(field).toHaveValue("Проверить обновление клиента\nпосле пятницы");
    await field.fill("");
    await save.click();
    await expect(panel.getByRole("status")).toHaveText("Заметка сохранена в Remnawave.");
    await expect(add).toBeVisible();
  });
}
