import { expect, test, type Locator } from "@playwright/test";

async function expectContainedBy(element: Locator, container: Locator): Promise<void> {
  const [elementBox, containerBox] = await Promise.all([
    element.boundingBox(),
    container.boundingBox(),
  ]);
  if (!elementBox || !containerBox) {
    throw new Error("Expected visible element and container bounds");
  }
  expect(elementBox.x).toBeGreaterThanOrEqual(containerBox.x - 1);
  expect(elementBox.x + elementBox.width).toBeLessThanOrEqual(
    containerBox.x + containerBox.width + 1
  );
}

async function enterDateTime(shell: Locator, value: string): Promise<void> {
  const clear = shell.getByRole("button", { name: /^Очистить дату:/ });
  if (await clear.count()) await clear.click();
  const [year, month, day, hour, minute] = value.split(/[-T:]/);
  for (const [part, text] of Object.entries({ year, month, day, hour, minute })) {
    await shell.locator(`[data-segment="${part}"]`).pressSequentially(text);
  }
}

test("broadcast editor is compact and history uses a sortable detail table", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/demo/runtime/admin/broadcast?theme_preview=dark");

  await expect(page.getByRole("heading", { name: "История рассылок" })).toBeVisible();
  const controls = page.locator(".broadcast-control-panel");
  await expect(controls).toHaveCount(4);
  const initialControlBoxes = await controls.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect())
  );
  expect(new Set(initialControlBoxes.map((box) => Math.round(box.top))).size).toBe(1);
  expect(new Set(initialControlBoxes.map((box) => Math.round(box.height))).size).toBe(1);
  const controlSurfaces = await controls.evaluateAll((elements) =>
    elements.map((element) => {
      const style = getComputedStyle(element);
      return `${style.backgroundColor}|${style.borderTopColor}|${style.borderTopWidth}`;
    })
  );
  expect(new Set(controlSurfaces).size).toBe(1);

  const scheduleControl = page.locator(".broadcast-schedule-control");
  await scheduleControl.getByRole("checkbox").click();
  await expect(scheduleControl.locator('input[type="datetime-local"]')).toHaveCount(0);
  const scheduleInput = scheduleControl.locator(".date-input");
  await expect(scheduleInput).toBeVisible();
  await expectContainedBy(scheduleInput.locator(".date-input-trigger"), scheduleInput);
  await expect(scheduleControl.getByText("Отправить позже", { exact: true })).toHaveCount(0);
  const primaryControls = page.locator(
    [
      ".broadcast-audience-control .admin-select-trigger",
      '.broadcast-channels .broadcast-channel:first-child [role="checkbox"]',
      ".broadcast-language-control .message-locale-tab:first-child",
      ".broadcast-schedule-control .date-input",
    ].join(", ")
  );
  await expect(primaryControls).toHaveCount(4);
  const primaryControlCenters = await primaryControls.evaluateAll((elements) =>
    elements.map((element) => {
      const box = element.getBoundingClientRect();
      return box.top + box.height / 2;
    })
  );
  expect(
    Math.max(...primaryControlCenters) - Math.min(...primaryControlCenters)
  ).toBeLessThanOrEqual(1);
  const scheduledControlBoxes = await controls.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect())
  );
  expect(scheduledControlBoxes.map((box) => Math.round(box.height))).toEqual(
    initialControlBoxes.map((box) => Math.round(box.height))
  );
  await scheduleControl.locator(".date-input-trigger").click();
  const calendar = page.locator(".date-input-popover");
  await expect(calendar).toBeVisible();
  await expect(calendar.locator(".date-input-day[data-disabled]").first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(calendar).toBeHidden();
  await enterDateTime(scheduleControl.locator(".date-input-shell"), "2020-01-01T00:00");
  await expect(scheduleInput).toHaveAttribute("aria-invalid", "true");
  await expect(scheduleInput).toHaveClass(/input-error/);
  await expect(scheduleControl).toHaveClass(/is-invalid/);
  await expect(scheduleControl.getByText("Время отправки должно быть в будущем")).toBeVisible();

  const rows = page.locator(".broadcast-history-row");
  await expect(rows).toHaveCount(3);
  await expect(page.locator(".broadcast-history-table")).toBeVisible();

  const createdHeader = page.getByRole("columnheader", { name: /Создана/ });
  await createdHeader.click();
  await expect(createdHeader).toHaveAttribute("aria-sort", "ascending");
  await createdHeader.click();
  await expect(createdHeader).toHaveAttribute("aria-sort", "none");
  await createdHeader.click();
  await expect(createdHeader).toHaveAttribute("aria-sort", "descending");

  const scheduledRow = rows.filter({ hasText: "Запланирована" }).first();
  await scheduledRow.click();
  const detail = page.getByRole("dialog");
  await expect(detail).toBeVisible();
  await expect(detail.getByRole("heading", { name: /Рассылка №/ })).toBeVisible();
  await expect(detail).toContainText("Пропустить заблокировавших бота");
  await detail.getByRole("button", { name: "Закрыть" }).last().click();
  await rows.filter({ hasText: "Завершена с ошибками" }).click();
  await page
    .getByRole("dialog", { name: "Рассылка №101" })
    .getByRole("button", { name: "Показать ошибки рассылки №101" })
    .click();
  const failures = page.getByRole("dialog", { name: "Ошибки рассылки №101" });
  await expect(failures).toBeVisible();
  await expect(failures.getByText("Пользователь заблокировал бота").first()).toBeVisible();
  await expect(failures.locator(".broadcast-failures-item")).toHaveCount(5);
  await expect(failures).toContainText(
    "О новой блокировке Telegram может сообщить только при попытке доставки"
  );
  await failures.getByRole("button", { name: "Закрыть" }).last().click();
  await expect(failures).toBeHidden();
});

test("broadcast history opens details on mobile and scheduled items can be edited and removed", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await page.goto("/demo/runtime/admin/broadcast?theme_preview=dark");

  const controls = page.locator(".broadcast-control-panel");
  await expect(controls).toHaveCount(4);
  const controlBoxes = await controls.evaluateAll((elements) =>
    elements.map((element) => element.getBoundingClientRect())
  );
  expect(new Set(controlBoxes.map((box) => Math.round(box.left))).size).toBe(1);
  expect(new Set(controlBoxes.map((box) => Math.round(box.top))).size).toBe(4);

  const scheduleControl = page.locator(".broadcast-schedule-control");
  await scheduleControl.getByRole("checkbox").click();
  const editorScheduleInput = scheduleControl.locator(".date-input");
  await expect(editorScheduleInput).toBeVisible();
  await expectContainedBy(scheduleControl, page.locator(".broadcast-setup-grid"));
  await expectContainedBy(editorScheduleInput, scheduleControl);
  await expectContainedBy(editorScheduleInput.locator(".date-input-trigger"), editorScheduleInput);
  expect(
    await editorScheduleInput.evaluate((node) => node.scrollWidth - node.clientWidth)
  ).toBeLessThanOrEqual(1);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(1);

  const rows = page.locator(".broadcast-history-row");
  await expect(rows).toHaveCount(3);
  const scheduledRow = rows.filter({ hasText: "Запланирована" }).first();
  await scheduledRow.click();

  const detail = page.getByRole("dialog");
  await expect(detail).toBeVisible();
  await detail.getByRole("button", { name: "Изменить время" }).click();
  await expect(detail.locator('input[type="datetime-local"]')).toHaveCount(0);
  const scheduleInput = detail.locator(".date-input");
  await expect(scheduleInput).toBeVisible();
  const rescheduleRow = detail.locator(".broadcast-reschedule-row");
  await expectContainedBy(rescheduleRow, detail.locator(".admin-broadcast-dialog"));
  await expectContainedBy(scheduleInput, rescheduleRow);
  await expectContainedBy(scheduleInput.locator(".date-input-trigger"), scheduleInput);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(1);
  await detail.locator(".date-input-trigger").click();
  const calendar = page.locator(".date-input-popover");
  await expect(calendar).toBeVisible();
  await expectContainedBy(calendar, page.locator("body"));
  await page.keyboard.press("Escape");
  await expect(calendar).toBeHidden();
  await expect(detail).toBeVisible();
  await enterDateTime(detail.locator(".date-input-shell"), "2020-01-01T00:00");
  await expect(scheduleInput).toHaveAttribute("aria-invalid", "true");
  await expect(scheduleInput).toHaveClass(/input-error/);
  await expect(detail.getByRole("button", { name: "Обновить" })).toBeDisabled();
  await expect(detail.getByText("Время отправки должно быть в будущем")).toBeVisible();
  await enterDateTime(detail.locator(".date-input-shell"), "2031-05-20T14:30");
  await expect(scheduleInput).not.toHaveAttribute("aria-invalid", "true");
  await detail.getByRole("button", { name: "Обновить" }).click();
  await expect(detail).toContainText("20.05.2031");

  page.once("dialog", (dialog) => dialog.accept());
  await detail.getByRole("button", { name: "Отменить и удалить" }).click();
  await expect(detail).toBeHidden();
  await expect(rows).toHaveCount(2);
});

test("broadcast delivery errors remain readable on a narrow screen", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 700 });
  await page.goto("/demo/runtime/admin/broadcast?theme_preview=dark");
  await page.locator(".broadcast-history-row").filter({ hasText: "Завершена с ошибками" }).click();
  await page.getByRole("button", { name: "Показать ошибки рассылки №101" }).click();
  const failures = page.getByRole("dialog", { name: "Ошибки рассылки №101" });
  await expect(failures).toBeVisible();
  await expect(failures.getByText("Пользователь №100241")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(1);
});
