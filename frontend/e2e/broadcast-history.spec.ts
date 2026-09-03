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
  const scheduleInput = scheduleControl.locator('input[type="datetime-local"]');
  await expect(scheduleInput).toBeVisible();
  await expect(scheduleControl.getByText("Отправить позже", { exact: true })).toHaveCount(0);
  const primaryControls = page.locator(
    [
      ".broadcast-audience-control .admin-select-trigger",
      '.broadcast-channels .broadcast-channel:first-child [role="checkbox"]',
      ".broadcast-language-control .message-locale-tab:first-child",
      '.broadcast-schedule-control input[type="datetime-local"]',
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
  const minimumSchedule = await scheduleInput.getAttribute("min");
  expect(minimumSchedule).not.toBeNull();
  expect(new Date(minimumSchedule || "").getTime()).toBeGreaterThan(Date.now() - 60_000);

  await scheduleInput.fill("2020-01-01T00:00");
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
});

test("broadcast history opens details on mobile and scheduled items can be edited and removed", async ({ page }) => {
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
  const editorScheduleInput = scheduleControl.locator('input[type="datetime-local"]');
  await expect(editorScheduleInput).toBeVisible();
  await expectContainedBy(scheduleControl, page.locator(".broadcast-setup-grid"));
  await expectContainedBy(editorScheduleInput, scheduleControl);
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
  const scheduleInput = detail.locator('input[type="datetime-local"]');
  await expect(scheduleInput).toBeVisible();
  const rescheduleRow = detail.locator(".broadcast-reschedule-row");
  await expectContainedBy(rescheduleRow, detail.locator(".admin-broadcast-dialog"));
  await expectContainedBy(scheduleInput, rescheduleRow);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  ).toBeLessThanOrEqual(1);
  await scheduleInput.fill("2020-01-01T00:00");
  await expect(scheduleInput).toHaveAttribute("aria-invalid", "true");
  await expect(scheduleInput).toHaveClass(/input-error/);
  await expect(detail.getByRole("button", { name: "Обновить" })).toBeDisabled();
  await expect(detail.getByText("Время отправки должно быть в будущем")).toBeVisible();
  await scheduleInput.fill("2031-05-20T14:30");
  await expect(scheduleInput).toHaveAttribute("aria-invalid", "false");
  await detail.getByRole("button", { name: "Обновить" }).click();
  await expect(detail).toContainText("20.05.2031");

  page.once("dialog", (dialog) => dialog.accept());
  await detail.getByRole("button", { name: "Отменить и удалить" }).click();
  await expect(detail).toBeHidden();
  await expect(rows).toHaveCount(2);
});
