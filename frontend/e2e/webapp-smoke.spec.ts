import { test, expect, type ConsoleMessage, type Locator, type Page } from "@playwright/test";

// Deterministic mock-smoke for the Svelte webapp (docs-demo build, mockApi, no
// backend). This is the standing UI regression gate for webapp/admin
// navigation, dialogs, dialog tabs, disclosure panels, activation handoff, and
// console health.

const APP_URL = "/demo/runtime/app/";
const DESKTOP_VIEWPORT = { width: 1280, height: 900 };
const MOBILE_VIEWPORT = { width: 390, height: 900 };

const NAV_TABS = [
  { label: "Главная", urlPart: "/demo/runtime/home" },
  { label: "Бонусы", urlPart: "/demo/runtime/invite" },
  { label: "Устройства", urlPart: "/demo/runtime/devices" },
  { label: "Поддержка", urlPart: "/demo/runtime/support" },
  { label: "Настройки", urlPart: "/demo/runtime/settings" },
] as const;

const CORE_ADMIN_SECTION_IDS = [
  "stats",
  "users",
  "payments",
  "promos",
  "ads",
  "broadcast",
  "logs",
  "support",
  "tariffs",
  "appearance",
  "translations",
  "backups",
  "settings",
] as const;

// Environmental noise that is not an app regression (no real backend / Telegram
// SDK / network in the mock). Keep this list tight: it must not mask app bugs.
const IGNORED_ERROR_PATTERNS: RegExp[] = [/favicon/i, /telegram\.org/i];

function isIgnoredError(text: string): boolean {
  return IGNORED_ERROR_PATTERNS.some((re) => re.test(text));
}

function trackErrors(page: Page, phase: () => string): string[] {
  const errors: string[] = [];
  page.on("console", (msg: ConsoleMessage) => {
    const location = msg.location();
    const where = location.url ? ` at ${location.url}:${location.lineNumber}` : "";
    if (msg.type() === "error" && !isIgnoredError(msg.text())) {
      errors.push(`[${phase()}] console.error${where}: ${msg.text()}`);
    }
    if (msg.type() === "warning" && /derived_inert/.test(msg.text())) {
      errors.push(`[${phase()}] console.warning${where}: ${msg.text()}`);
    }
  });
  page.on("pageerror", (err: Error) => {
    if (!isIgnoredError(err.message)) errors.push(`[${phase()}] pageerror: ${err.message}`);
  });
  return errors;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function adminSectionButton(page: Page, id: string): Locator {
  return page.locator(`[data-admin-section="${id}"]`);
}

function webappAction(page: Page, id: string): Locator {
  return page.locator(`[data-webapp-action="${id}"]:visible`);
}

function activeAdminSection(page: Page, id: string): Locator {
  return page.locator(`.admin-section-stage[data-admin-active-section="${id}"]:not([inert])`);
}

async function assertNoDuplicateIds(page: Page, phase: string): Promise<void> {
  const duplicates = await page.locator("[id]").evaluateAll((elements) => {
    const seen = new Map<string, number>();
    for (const element of elements) {
      const html = element as HTMLElement;
      if (html.closest("[inert]")) continue;
      const id = html.id;
      if (!id) continue;
      seen.set(id, (seen.get(id) ?? 0) + 1);
    }
    return Array.from(seen.entries())
      .filter(([, count]) => count > 1)
      .map(([id, count]) => `${id} (${count})`);
  });
  expect(duplicates, `${phase}: element ids must be unique`).toEqual([]);
}

async function assertInteractiveControlsNamed(page: Page, phase: string): Promise<void> {
  const violations = await page
    .locator(
      [
        "button",
        "a[href]",
        '[role="button"]',
        '[role="link"]',
        '[role="tab"]',
        '[role="radio"]',
        '[role="checkbox"]',
        '[role="menuitem"]',
      ].join(", ")
    )
    .evaluateAll((elements) => {
      const isVisible = (element: Element): boolean => {
        const html = element as HTMLElement;
        const style = window.getComputedStyle(html);
        const rect = html.getBoundingClientRect();
        return (
          !html.closest("[inert]") &&
          !html.closest('[aria-hidden="true"]') &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0
        );
      };
      const labelFromIds = (ids: string): string =>
        ids
          .split(/\s+/)
          .map((id) => document.getElementById(id)?.textContent ?? "")
          .join(" ")
          .replace(/\s+/g, " ")
          .trim();
      const accessibleName = (element: Element): string => {
        const ariaLabel = element.getAttribute("aria-label")?.trim();
        if (ariaLabel) return ariaLabel;
        const labelledBy = element.getAttribute("aria-labelledby")?.trim();
        if (labelledBy) {
          const labelledText = labelFromIds(labelledBy);
          if (labelledText) return labelledText;
        }
        const title = element.getAttribute("title")?.trim();
        if (title) return title;
        return (element.textContent ?? "").replace(/\s+/g, " ").trim();
      };
      const describe = (element: Element): string => {
        const html = element as HTMLElement;
        const role = html.getAttribute("role");
        const id = html.id ? `#${html.id}` : "";
        const className = (html.getAttribute("class") ?? "")
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .join(".");
        return `${html.tagName.toLowerCase()}${id}${role ? `[role=${role}]` : ""}${className ? `.${className}` : ""}`;
      };
      return elements
        .filter(isVisible)
        .filter((element) => !accessibleName(element))
        .map(describe);
    });
  expect(violations, `${phase}: visible interactive controls must have an accessible name`).toEqual(
    []
  );
}

async function assertNoNestedInteractiveControls(page: Page, phase: string): Promise<void> {
  const violations = await page
    .locator(
      [
        "button",
        "a[href]",
        '[role="button"]',
        '[role="link"]',
        '[role="tab"]',
        '[role="radio"]',
        '[role="checkbox"]',
        '[role="switch"]',
      ].join(", ")
    )
    .evaluateAll((elements) => {
      const interactiveSelector = [
        "button",
        "a[href]",
        "input:not([type='hidden'])",
        "select",
        "textarea",
        '[role="button"]',
        '[role="link"]',
        '[role="tab"]',
        '[role="radio"]',
        '[role="checkbox"]',
        '[role="switch"]',
        '[role="menuitem"]',
      ].join(", ");
      const isVisible = (element: Element): boolean => {
        const html = element as HTMLElement;
        const style = window.getComputedStyle(html);
        const rect = html.getBoundingClientRect();
        return (
          !html.closest("[inert]") &&
          !html.closest('[aria-hidden="true"]') &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0
        );
      };
      const describe = (element: Element): string => {
        const html = element as HTMLElement;
        const role = html.getAttribute("role");
        const id = html.id ? `#${html.id}` : "";
        const className = (html.getAttribute("class") ?? "")
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .join(".");
        return `${html.tagName.toLowerCase()}${id}${role ? `[role=${role}]` : ""}${className ? `.${className}` : ""}`;
      };
      return elements.filter(isVisible).flatMap((element) => {
        const nested = Array.from(element.querySelectorAll(interactiveSelector)).filter(isVisible);
        return nested.length
          ? [`${describe(element)} contains ${nested.map(describe).slice(0, 3).join(", ")}`]
          : [];
      });
    });
  expect(violations, `${phase}: interactive controls must not contain nested controls`).toEqual([]);
}

async function assertImagesNamed(page: Page, phase: string): Promise<void> {
  const violations = await page.locator("img").evaluateAll((elements) =>
    elements
      .filter((element) => {
        const image = element as HTMLImageElement;
        const style = window.getComputedStyle(image);
        const rect = image.getBoundingClientRect();
        return (
          !image.closest("[inert]") &&
          !image.closest('[aria-hidden="true"]') &&
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          rect.width > 0 &&
          rect.height > 0
        );
      })
      .filter((element) => {
        const image = element as HTMLImageElement;
        return (
          image.getAttribute("role") !== "presentation" &&
          image.getAttribute("aria-hidden") !== "true" &&
          !image.hasAttribute("alt") &&
          !image.hasAttribute("aria-label") &&
          !image.hasAttribute("aria-labelledby")
        );
      })
      .map((element) => {
        const image = element as HTMLImageElement;
        return `img${image.className ? `.${String(image.className).split(/\s+/).filter(Boolean).slice(0, 2).join(".")}` : ""}`;
      })
  );
  expect(violations, `${phase}: visible images must have alt text or be marked decorative`).toEqual(
    []
  );
}

async function assertFormFieldsNamed(page: Page, phase: string): Promise<void> {
  await assertNoDuplicateIds(page, phase);
  await assertInteractiveControlsNamed(page, phase);
  await assertNoNestedInteractiveControls(page, phase);
  await assertImagesNamed(page, phase);

  const violations = await page
    .locator('input:not([type="hidden"]), textarea, select')
    .evaluateAll((elements) =>
      elements
        .filter((element) => {
          const field = element as HTMLElement;
          const style = window.getComputedStyle(field);
          const rect = field.getBoundingClientRect();
          return (
            !field.closest("[inert]") &&
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0
          );
        })
        .filter((element) => {
          const field = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
          return !field.id && !field.name;
        })
        .map((element) => {
          const field = element as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement;
          const label = field.getAttribute("aria-label") || field.getAttribute("placeholder") || "";
          return `${field.tagName.toLowerCase()}${field.type ? `[type=${field.type}]` : ""}${label ? ` "${label}"` : ""}`;
        })
    );
  expect(violations, `${phase}: visible form fields must have id or name`).toEqual([]);
}

async function openAdminSection(page: Page, id: string): Promise<Locator> {
  const button = adminSectionButton(page, id);
  await expect(button, `admin section button: ${id}`).toBeVisible();
  await button.click();
  await expect(page).toHaveURL(new RegExp(`/demo/runtime/admin/${escapeRegExp(id)}(?:$|[/?#])`));
  const stage = activeAdminSection(page, id);
  await expect(stage, `active admin section: ${id}`).toBeVisible();
  await assertFormFieldsNamed(page, `admin-section:${id}`);
  return stage;
}

async function closeDialog(card: Locator): Promise<void> {
  await card.locator(".dialog-head button").click();
  await expect(card).toBeHidden();
}

async function clickFirstVisibleEnabled(locator: Locator): Promise<boolean> {
  const count = await locator.count();
  for (let index = 0; index < count; index += 1) {
    const target = locator.nth(index);
    if (!(await target.isVisible())) continue;
    if (await target.isDisabled()) continue;
    await target.scrollIntoViewIfNeeded();
    await expect(target).toBeEnabled();
    await target.click();
    return true;
  }
  return false;
}

async function clickCardBody(page: Page, card: Locator, phase: string): Promise<void> {
  await card.scrollIntoViewIfNeeded();
  const box = await card.boundingBox();
  expect(box, `${phase}: card must have a clickable box`).not.toBeNull();
  if (!box) return;
  await page.mouse.click(box.x + Math.min(24, box.width / 2), box.y + Math.min(24, box.height / 2));
}

async function swipeUp(page: Page, target: Locator, phase: string): Promise<void> {
  const box = await target.boundingBox();
  const viewport = page.viewportSize();
  expect(box, `${phase}: swipe target must have a bounding box`).not.toBeNull();
  expect(viewport, `${phase}: viewport must be available`).not.toBeNull();
  if (!box || !viewport) return;

  const x = Math.round(Math.min(viewport.width - 20, Math.max(20, box.x + box.width / 2)));
  const startY = Math.round(
    Math.min(viewport.height - 60, Math.max(100, box.y + Math.min(box.height - 20, 420)))
  );
  const endY = Math.max(60, startY - 420);
  const session = await page.context().newCDPSession(page);
  try {
    await session.send("Input.dispatchTouchEvent", {
      type: "touchStart",
      touchPoints: [{ x, y: startY }],
    });
    for (let y = startY - 40; y >= endY; y -= 40) {
      await session.send("Input.dispatchTouchEvent", {
        type: "touchMove",
        touchPoints: [{ x, y }],
      });
      await page.waitForTimeout(20);
    }
    await session.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  } finally {
    await session.detach();
  }
}

async function assertUserTicketScrolling(page: Page, nav: Locator): Promise<void> {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await nav.getByRole("button", { name: "Поддержка", exact: true }).click();
  await page.locator(".ticket-card").first().click();

  const messageViewport = page.locator(
    ".support-ticket-screen .support-message-scroll > .scroll-area__viewport"
  );
  const composer = page.locator(".support-ticket-screen .ticket-composer");
  await expect(composer).toBeVisible();
  const readReceipt = page
    .locator('.support-ticket-screen .ticket-message-receipt[title="Прочитано"]')
    .first();
  await expect(readReceipt).toBeVisible();
  await expect(readReceipt.locator(".lucide-check-check")).toBeVisible();
  await composer.locator("textarea").fill("Проверка статуса доставки");
  await composer.getByRole("button").click();
  const sentReceipt = page
    .locator('.support-ticket-screen .ticket-message-receipt[title="Отправлено"]')
    .last();
  await expect(sentReceipt).toBeVisible();
  await expect(sentReceipt.locator(".lucide-check")).toBeVisible();
  await page.waitForTimeout(220);
  await expect
    .poll(() => messageViewport.evaluate((element) => element.scrollHeight - element.clientHeight))
    .toBeGreaterThan(0);

  await messageViewport.evaluate((element) => {
    element.scrollTop = 0;
  });
  await messageViewport.hover();
  await page.mouse.wheel(0, 480);
  await expect
    .poll(() => messageViewport.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);

  await page.setViewportSize(MOBILE_VIEWPORT);
  await messageViewport.evaluate((element) => {
    element.scrollTop = 0;
  });
  await swipeUp(page, messageViewport, "webapp-support:mobile-scroll");
  await expect
    .poll(() => messageViewport.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await expect(composer).toBeInViewport();

  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.locator(".support-back-button").click();
  await expect(page.locator(".support-screen")).toBeVisible();
}

async function assertAdminTicketScrolling(page: Page, supportDialog: Locator): Promise<void> {
  const bodyViewport = supportDialog.locator(
    ":scope > .dialog-body-scroll > .scroll-area__viewport"
  );
  const messageScroll = supportDialog.locator(".support-admin-message-scroll");
  const messageViewport = messageScroll.locator(":scope > .scroll-area__viewport");
  const composer = supportDialog.locator(".support-admin-composer");

  await page.waitForTimeout(220);
  await expect
    .poll(() => bodyViewport.evaluate((element) => element.scrollHeight - element.clientHeight))
    .toBeGreaterThan(0);
  await bodyViewport.evaluate((element) => {
    element.scrollTop = 0;
  });
  await messageScroll.hover();
  await page.mouse.wheel(0, 480);
  await expect.poll(() => bodyViewport.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);

  await page.setViewportSize(MOBILE_VIEWPORT);
  await expect
    .poll(() => messageViewport.evaluate((element) => getComputedStyle(element).overflowY))
    .toBe("visible");
  await bodyViewport.evaluate((element) => {
    element.scrollTop = 0;
  });
  await swipeUp(page, messageScroll, "admin-support:mobile-scroll");
  await expect.poll(() => bodyViewport.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  await expect.poll(() => page.locator(".dialog").evaluate((element) => element.scrollTop)).toBe(0);

  const modalCoversHeader = await page.evaluate(() => {
    const header = document.querySelector(".admin-header");
    if (!(header instanceof HTMLElement)) return false;
    const rect = header.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return Boolean(hit?.closest(".dialog"));
  });
  expect(modalCoversHeader, "admin-support: modal must stay above the section header").toBe(true);

  await bodyViewport.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(composer).toBeInViewport();
  await bodyViewport.evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.setViewportSize(DESKTOP_VIEWPORT);
}

async function exerciseDialogTabs(
  card: Locator,
  expectedCount: number,
  setPhase: (value: string) => void,
  phasePrefix: string
): Promise<void> {
  const tabs = card.locator(".admin-tabs-trigger");
  await expect(tabs).toHaveCount(expectedCount);
  for (let index = 0; index < expectedCount; index += 1) {
    setPhase(`${phasePrefix}:tab:${index + 1}`);
    const tab = tabs.nth(index);
    await tab.scrollIntoViewIfNeeded();
    await tab.click();
    await expect
      .poll(async () => {
        const dataState = await tab.getAttribute("data-state");
        const ariaSelected = await tab.getAttribute("aria-selected");
        return dataState === "active" || ariaSelected === "true";
      })
      .toBe(true);
    await expect(card.locator(".admin-tabs-content:visible").first()).toBeVisible();
    await assertFormFieldsNamed(card.page(), `${phasePrefix}:tab:${index + 1}`);
  }
}

async function assertMobileExtendTariffSelectDoesNotTapThrough(
  page: Page,
  userDialog: Locator,
  phase: string
): Promise<void> {
  await page.setViewportSize(MOBILE_VIEWPORT);

  const actionsTab = userDialog.locator(".admin-tabs-trigger").nth(3);
  await actionsTab.click();
  const actionsPanel = userDialog.locator(".admin-actions-tab");
  await expect(actionsPanel).toBeVisible();

  await page.evaluate(() => {
    const trackedWindow = window as typeof window & {
      __adminResetTrialClickGuardAttached?: boolean;
      __adminResetTrialClicks?: number;
    };
    trackedWindow.__adminResetTrialClicks = 0;
    if (trackedWindow.__adminResetTrialClickGuardAttached) return;
    trackedWindow.__adminResetTrialClickGuardAttached = true;
    document.addEventListener(
      "click",
      (event) => {
        const target = event.target;
        if (target instanceof Element && target.closest(".admin-reset-trial-btn")) {
          trackedWindow.__adminResetTrialClicks = (trackedWindow.__adminResetTrialClicks ?? 0) + 1;
        }
      },
      true
    );
  });

  const resetTrialButton = actionsPanel.locator(".admin-reset-trial-btn");
  await expect(resetTrialButton).toBeVisible();
  await expect(resetTrialButton).toBeEnabled();

  const extendTariffTrigger = actionsPanel.locator(".admin-user-extend-tariff-select");
  await expect(extendTariffTrigger).toBeVisible();
  await expect(extendTariffTrigger).toBeEnabled();
  await extendTariffTrigger.click();

  const selectContent = page.locator(".admin-select-content:visible").last();
  await expect(selectContent).toBeVisible();

  const items = selectContent.locator(".admin-select-item");
  const itemCount = await items.count();
  expect(itemCount, `${phase}: extend tariff select should expose choices`).toBeGreaterThan(1);

  const targetItem = items.nth(Math.min(2, itemCount - 1));
  await expect(targetItem).toBeVisible();
  const targetLabel = (await targetItem.locator("span").first().innerText()).trim();
  const itemReceivesPointer = await targetItem.evaluate((item) => {
    const rect = item.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return Boolean(hit && (hit === item || item.contains(hit)));
  });
  expect(itemReceivesPointer, `${phase}: select option must receive pointer events`).toBe(true);

  await targetItem.click();
  await expect(extendTariffTrigger).toContainText(targetLabel);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const trackedWindow = window as typeof window & { __adminResetTrialClicks?: number };
        return trackedWindow.__adminResetTrialClicks ?? 0;
      })
    )
    .toBe(0);
}

async function openUserDetailFromCurrentSection(
  page: Page,
  setPhase: (value: string) => void,
  phasePrefix: string,
  options: { checkMobileTariffTapThrough?: boolean } = {}
): Promise<void> {
  const userDialog = page.locator(".dialog-card.admin-user-dialog");
  setPhase(`${phasePrefix}:user-card`);
  await expect(userDialog).toBeVisible();
  await assertFormFieldsNamed(page, `${phasePrefix}:user-card`);
  await exerciseDialogTabs(userDialog, 4, setPhase, `${phasePrefix}:user-tabs`);

  setPhase(`${phasePrefix}:user-avatar`);
  if (
    await clickFirstVisibleEnabled(
      userDialog.locator(".admin-avatar-preview-trigger:not(:disabled)")
    )
  ) {
    const avatarDialog = page.locator(".dialog-card.admin-avatar-dialog");
    await expect(avatarDialog).toBeVisible();
    await assertFormFieldsNamed(page, `${phasePrefix}:user-avatar`);
    await closeDialog(avatarDialog);
  }

  setPhase(`${phasePrefix}:user-referrals`);
  if (
    await clickFirstVisibleEnabled(userDialog.locator('[data-admin-action="open-user-referrals"]'))
  ) {
    const referralsDialog = page.locator(".dialog-card.admin-user-referrals-dialog");
    await expect(referralsDialog).toBeVisible();
    await assertFormFieldsNamed(page, `${phasePrefix}:user-referrals`);
    await closeDialog(referralsDialog);
  }

  const actionsTab = userDialog.locator(".admin-tabs-trigger").nth(3);
  await actionsTab.click();
  const actionsPanel = userDialog.locator(".admin-actions-tab");
  await expect(actionsPanel).toBeVisible();
  await assertFormFieldsNamed(page, `${phasePrefix}:user-actions`);

  if (options.checkMobileTariffTapThrough) {
    setPhase(`${phasePrefix}:mobile-extend-tariff-select`);
    await assertMobileExtendTariffSelectDoesNotTapThrough(
      page,
      userDialog,
      `${phasePrefix}:mobile-extend-tariff-select`
    );
  }

  setPhase(`${phasePrefix}:message-confirm`);
  await actionsPanel.locator("textarea").fill("E2E smoke message");
  await actionsPanel.locator('[data-admin-action="request-user-message"]').click();
  const messageDialog = page.locator(".dialog-card.admin-user-message-confirm-dialog");
  await expect(messageDialog).toBeVisible();
  await assertFormFieldsNamed(page, `${phasePrefix}:message-confirm`);
  await closeDialog(messageDialog);

  setPhase(`${phasePrefix}:ban-confirm`);
  await actionsPanel.locator('[data-admin-action="request-user-ban-toggle"]').click();
  const banDialog = page.locator(".dialog-card.admin-user-ban-confirm-dialog");
  await expect(banDialog).toBeVisible();
  await assertFormFieldsNamed(page, `${phasePrefix}:ban-confirm`);
  await closeDialog(banDialog);

  setPhase(`${phasePrefix}:delete-confirm`);
  await actionsPanel.locator('[data-admin-action="request-user-delete"]').click();
  const deleteDialog = page.locator(".dialog-card.admin-user-delete-dialog");
  await expect(deleteDialog).toBeVisible();
  await assertFormFieldsNamed(page, `${phasePrefix}:delete-confirm`);
  await closeDialog(deleteDialog);

  await closeDialog(userDialog);
}

async function exerciseSettingsDisclosures(stage: Locator): Promise<void> {
  const sectionTriggers = stage.locator(".admin-accordion-trigger");
  const sectionCount = await sectionTriggers.count();
  for (let index = 0; index < sectionCount; index += 1) {
    const trigger = sectionTriggers.nth(index);
    if ((await trigger.getAttribute("data-state")) === "closed") {
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();
    }
  }

  const subsectionTriggers = stage.locator(".admin-settings-subsection-trigger");
  const subsectionCount = await subsectionTriggers.count();
  for (let index = 0; index < subsectionCount; index += 1) {
    const trigger = subsectionTriggers.nth(index);
    if ((await trigger.getAttribute("data-state")) === "closed") {
      await trigger.scrollIntoViewIfNeeded();
      await trigger.click();
    }
  }
}

async function exerciseWebappDialogs(
  page: Page,
  nav: Locator,
  setPhase: (value: string) => void
): Promise<void> {
  setPhase("webapp-payment-modal");
  await nav.getByRole("button", { name: "Главная", exact: true }).click();
  const paymentOpened = await clickFirstVisibleEnabled(webappAction(page, "open-payment"));
  expect(paymentOpened).toBe(true);
  const paymentDialog = page.locator(".dialog-card.webapp-payment-dialog");
  await expect(paymentDialog).toBeVisible();
  await assertFormFieldsNamed(page, "webapp-payment-modal");
  const tariffRows = paymentDialog.locator(".tariff-row");
  if ((await tariffRows.count()) > 0) {
    await tariffRows.first().click();
    const nextButton = paymentDialog.locator(".payment-submit-button").first();
    if (!(await nextButton.isDisabled())) {
      await nextButton.click();
      await expect(paymentDialog.locator(".period-card").first()).toBeVisible();
      await assertFormFieldsNamed(page, "webapp-payment-modal:checkout");
    }
  } else {
    await expect(paymentDialog.locator(".payment-dialog-body")).toBeVisible();
  }
  await closeDialog(paymentDialog);

  setPhase("webapp-tariff-change-modal");
  if (await clickFirstVisibleEnabled(webappAction(page, "open-tariff-change"))) {
    const changeDialog = page.locator(".dialog-card.webapp-tariff-change-dialog");
    await expect(changeDialog).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-tariff-change-modal");
    const targetRows = changeDialog.locator(".tariff-action-card");
    if ((await targetRows.count()) > 0) {
      await targetRows.first().click();
    }
    const changeSubmit = changeDialog.locator(".payment-submit-button").first();
    if ((await changeSubmit.count()) > 0 && !(await changeSubmit.isDisabled())) {
      await changeSubmit.click();
      const confirmDialog = page.locator(".dialog-card.webapp-tariff-change-confirm-dialog");
      await expect(confirmDialog).toBeVisible();
      await assertFormFieldsNamed(page, "webapp-tariff-change-confirm-modal");
      await closeDialog(confirmDialog);
    }
    if (await changeDialog.isVisible()) {
      await closeDialog(changeDialog);
    }
  }

  setPhase("webapp-regular-topup-modal");
  if (await clickFirstVisibleEnabled(webappAction(page, "open-regular-topup"))) {
    const topupDialog = page.locator(".dialog-card.webapp-topup-dialog");
    await expect(topupDialog).toBeVisible();
    await expect(topupDialog.locator(".payment-dialog-body")).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-regular-topup-modal");
    await closeDialog(topupDialog);
  }

  setPhase("webapp-premium-topup-modal");
  if (await clickFirstVisibleEnabled(webappAction(page, "open-premium-topup"))) {
    const topupDialog = page.locator(".dialog-card.webapp-topup-dialog");
    await expect(topupDialog).toBeVisible();
    await expect(topupDialog.locator(".payment-dialog-body")).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-premium-topup-modal");
    await closeDialog(topupDialog);
  }

  setPhase("webapp-device-modals");
  await nav.getByRole("button", { name: "Устройства", exact: true }).click();
  if (await clickFirstVisibleEnabled(webappAction(page, "open-device-topup"))) {
    const deviceTopupDialog = page.locator(".dialog-card.webapp-device-topup-dialog");
    await expect(deviceTopupDialog).toBeVisible();
    await expect(deviceTopupDialog.locator(".payment-dialog-body")).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-device-topup-modal");
    await closeDialog(deviceTopupDialog);
  }
  if (await clickFirstVisibleEnabled(webappAction(page, "open-device-disconnect"))) {
    const deviceDisconnectDialog = page.locator(".dialog-card.webapp-device-disconnect-dialog");
    await expect(deviceDisconnectDialog).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-device-disconnect-modal");
    await closeDialog(deviceDisconnectDialog);
  }

  setPhase("webapp-account-modals");
  await nav.getByRole("button", { name: "Настройки", exact: true }).click();
  if (await clickFirstVisibleEnabled(webappAction(page, "open-set-password"))) {
    const setPasswordDialog = page.locator(".dialog-card.webapp-set-password-dialog");
    await expect(setPasswordDialog).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-set-password-modal");
    const inputs = setPasswordDialog.locator('input[type="password"]');
    await inputs.nth(0).fill("DemoPassword42");
    await inputs.nth(1).fill("DemoPassword42");
    await setPasswordDialog.locator(".payment-submit-button").click();
    const codeDialog = page.locator(".webapp-set-password-code-dialog");
    await expect(codeDialog).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-set-password-code-modal");
    await codeDialog.locator("header button").click();
    await expect(codeDialog).toBeHidden();
  }
  if (await clickFirstVisibleEnabled(webappAction(page, "open-link-email"))) {
    const linkEmailDialog = page.locator(".dialog-card.webapp-link-email-dialog");
    await expect(linkEmailDialog).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-link-email-modal");
    await linkEmailDialog.locator('input[type="email"]').fill("demo-e2e@example.test");
    await linkEmailDialog.locator(".payment-submit-button").click();
    const codeDialog = page.locator(".webapp-link-email-code-dialog");
    await expect(codeDialog).toBeVisible();
    await assertFormFieldsNamed(page, "webapp-link-email-code-modal");
    await codeDialog.locator("header button").click();
    await expect(codeDialog).toBeHidden();
  }
}

async function exerciseActivationSuccessHandoff(
  page: Page,
  setPhase: (value: string) => void
): Promise<void> {
  setPhase("webapp-activation-success-dialog");
  await page.evaluate(() => {
    localStorage.setItem(
      "rw_webapp_activation_handoff_v1",
      JSON.stringify({
        pending: {
          kind: "initial_subscription",
          source: "e2e",
          paymentId: "e2e",
          userKey: "",
          startedAt: Date.now(),
        },
        acknowledged: null,
      })
    );
  });
  await page.goto(APP_URL);
  const activationDialog = page.locator(".dialog-card.webapp-activation-success-dialog");
  await expect(activationDialog).toBeVisible();
  await assertFormFieldsNamed(page, "webapp-activation-success-dialog");
  await closeDialog(activationDialog);
  await expect(page.locator(".dialog-card:visible")).toHaveCount(0);
}

test("support ticket conversations scroll on desktop and mobile", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(APP_URL);
  const nav = page.locator("nav.bottom-nav");
  await expect(nav).toBeVisible();

  await assertUserTicketScrolling(page, nav);

  await nav.locator(".rail-admin-entry").click();
  await adminSectionButton(page, "support").click();
  await page.locator(".support-inbox-row[data-ticket-id]").first().click();
  const supportDialog = page.locator(".dialog-card.support-ticket-dialog");
  await expect(supportDialog).toBeVisible();
  await assertAdminTicketScrolling(page, supportDialog);
});

test("webapp and admin sections, dialogs, tabs stay interactive without console errors", async ({
  page,
}) => {
  let phase = "boot";
  const setPhase = (value: string) => {
    phase = value;
  };
  const errors = trackErrors(page, () => phase);

  setPhase("boot");
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(APP_URL);
  const nav = page.locator("nav.bottom-nav");
  await expect(nav).toBeVisible();
  await expect(page.getByRole("button", { name: "Сменить тариф" })).toBeVisible();
  await assertFormFieldsNamed(page, "boot");

  setPhase("bottom-nav");
  for (const tab of NAV_TABS) {
    const button = nav.getByRole("button", { name: tab.label, exact: true });
    await button.click();
    await expect(page).toHaveURL(new RegExp(escapeRegExp(tab.urlPart)));
    await expect(button).toHaveClass(/active/);
    await assertFormFieldsNamed(page, `bottom-nav:${tab.urlPart}`);
  }

  await exerciseWebappDialogs(page, nav, setPhase);

  setPhase("admin-entry");
  await nav.getByRole("button", { name: "Админ-панель", exact: true }).click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/stats/);
  const adminSidebar = page.locator("aside.admin-sidebar");
  await expect(adminSidebar).toBeVisible();

  setPhase("admin-section-registry");
  for (const id of CORE_ADMIN_SECTION_IDS) {
    await expect(adminSectionButton(page, id), `core admin section exists: ${id}`).toBeVisible();
  }

  for (const id of CORE_ADMIN_SECTION_IDS) {
    setPhase(`admin-section:${id}`);
    await openAdminSection(page, id);
  }

  setPhase("admin-broadcast:shortcode-picker");
  await openAdminSection(page, "broadcast");
  const shortcodeToggle = page.locator(".broadcast-tool-shortcode");
  await expect(shortcodeToggle).toBeVisible();
  await shortcodeToggle.click();
  const shortcodeList = page.locator(".broadcast-shortcode-list");
  await expect(shortcodeList).toBeVisible();
  await expect(
    shortcodeList.locator(".broadcast-shortcode-scroll .scroll-area__viewport")
  ).toBeVisible();
  await shortcodeList.locator(".broadcast-shortcode-item").first().click();
  await expect(page.locator(".broadcast-surface .broadcast-chip").first()).toBeVisible();
  await page.locator("[data-broadcast-source-toggle]").click();
  const broadcastSource = page.locator("textarea.broadcast-source");
  await expect(broadcastSource).toBeVisible();
  await broadcastSource.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement;
    textarea.focus();
    textarea.setSelectionRange(0, textarea.value.length);
  });
  await page.locator('[data-broadcast-format="bold"]').click();
  await expect(broadcastSource).toHaveValue("<b>{first_name}</b>");
  await broadcastSource.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement;
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  });
  await page.locator('[data-broadcast-format="link"]').click();
  await expect(broadcastSource).toHaveValue('<b>{first_name}</b><a href="https://">https://</a>');
  await page.locator("[data-broadcast-source-toggle]").click();
  await expect(page.locator(".broadcast-surface .broadcast-chip").first()).toBeVisible();

  setPhase("admin-users:filter-dialog");
  await openAdminSection(page, "users");
  await page.setViewportSize(MOBILE_VIEWPORT);
  await expect(page.locator(".admin-users-filter-toggle")).toBeVisible();
  await page.locator(".admin-users-filter-toggle").click();
  const usersFilterDialog = page.locator(".dialog-card.admin-users-filter-dialog");
  await expect(usersFilterDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-users:filter-dialog");
  await closeDialog(usersFilterDialog);
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await expect(adminSidebar).toBeVisible();

  setPhase("admin-users:row-card");
  await page.locator("tr[data-user-id]").first().click();
  await openUserDetailFromCurrentSection(page, setPhase, "admin-users", {
    checkMobileTariffTapThrough: true,
  });
  await page.setViewportSize(DESKTOP_VIEWPORT);

  setPhase("admin-payments:payment-dialog");
  await openAdminSection(page, "payments");
  await page.locator(".admin-payment-id-btn").first().click();
  const paymentDialog = page.locator(".dialog-card.admin-payment-dialog");
  await expect(paymentDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-payments:payment-dialog");
  await closeDialog(paymentDialog);

  setPhase("admin-payments:user-card");
  await page.locator(".admin-payments-user-btn").first().click();
  await openUserDetailFromCurrentSection(page, setPhase, "admin-payments");

  setPhase("admin-codes:create-dialog");
  await openAdminSection(page, "promos");
  await page.locator('[data-admin-action="create-code"]').click();
  const createCodeDialog = page.locator(
    ".dialog-card.admin-promo-dialog:not(.admin-promo-edit-dialog)"
  );
  await expect(createCodeDialog).toBeVisible();
  await expect(createCodeDialog.locator(".admin-promo-effect-row")).toHaveCount(4);
  await assertFormFieldsNamed(page, "admin-codes:create-dialog");
  await closeDialog(createCodeDialog);

  setPhase("admin-codes:editor-dialog");
  await page.locator('[data-admin-action="open-code-settings"]').first().click();
  const codeEditorDialog = page.locator(".dialog-card.admin-promo-edit-dialog");
  await expect(codeEditorDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-codes:editor-dialog");
  await exerciseDialogTabs(codeEditorDialog, 2, setPhase, "admin-codes:tabs");
  await expect(codeEditorDialog.locator(".admin-promo-activations-tab")).toBeVisible();
  await assertFormFieldsNamed(page, "admin-codes:activations-tab");

  setPhase("admin-codes:activation-user-card");
  if (await clickFirstVisibleEnabled(codeEditorDialog.locator(".admin-promos-user-btn"))) {
    await openUserDetailFromCurrentSection(page, setPhase, "admin-codes");
  }
  await closeDialog(codeEditorDialog);

  setPhase("admin-ads:create-dialog");
  await openAdminSection(page, "ads");
  await page.locator('[data-admin-action="create-ad"]').click();
  const adDialog = page.locator(".dialog-card.admin-ad-dialog");
  await expect(adDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-ads:create-dialog");
  await closeDialog(adDialog);

  setPhase("admin-support:ticket-dialog");
  await openAdminSection(page, "support");
  await page.locator(".support-inbox-row[data-ticket-id]").first().click();
  const supportDialog = page.locator(".dialog-card.support-ticket-dialog");
  await expect(supportDialog).toBeVisible();
  await expect(supportDialog.locator(".support-admin-composer")).toBeVisible();
  await assertFormFieldsNamed(page, "admin-support:ticket-dialog");

  setPhase("admin-support:user-card");
  if (
    await clickFirstVisibleEnabled(
      supportDialog.locator('[data-admin-action="open-support-user-card"]')
    )
  ) {
    await openUserDetailFromCurrentSection(page, setPhase, "admin-support");
  }
  await closeDialog(supportDialog);

  setPhase("admin-tariffs:create-dialog");
  await openAdminSection(page, "tariffs");
  await page.locator('[data-admin-action="create-tariff"]').click();
  const tariffDialog = page.locator(".dialog-card.admin-tariff-dialog");
  await expect(tariffDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-tariffs:create-dialog");
  await exerciseDialogTabs(tariffDialog, 5, setPhase, "admin-tariffs:create-tabs");
  await closeDialog(tariffDialog);

  setPhase("admin-tariffs:edit-dialog");
  await page.locator('[data-admin-action="open-tariff-editor"]').first().click();
  await expect(tariffDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-tariffs:edit-dialog");
  await exerciseDialogTabs(tariffDialog, 5, setPhase, "admin-tariffs:edit-tabs");

  setPhase("admin-tariffs:edit-save");
  await tariffDialog.getByRole("tab").nth(0).click();
  await tariffDialog.locator('input[placeholder="100"]:visible').fill("750");
  await tariffDialog.getByRole("tab").nth(1).click();
  await tariffDialog.locator('input[placeholder="299"]:visible').first().fill("250");
  await tariffDialog.locator(".admin-dialog-actions").getByRole("button").last().click();
  await expect(tariffDialog).toBeHidden();
  await expect(page.locator(".admin-tariff-card").first()).toContainText("750 GB");

  setPhase("admin-tariffs:delete-dialog");
  await page.locator('[data-admin-action="open-tariff-delete"]').first().click();
  const tariffDeleteDialog = page.locator(".dialog-card.admin-tariff-delete-dialog");
  await expect(tariffDeleteDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-tariffs:delete-dialog");
  await closeDialog(tariffDeleteDialog);

  setPhase("admin-appearance:panels");
  const appearanceStage = await openAdminSection(page, "appearance");
  await expect(appearanceStage.locator(".appearance-stack")).toBeVisible();
  await expect(appearanceStage.locator(".appearance-logo-grid").first()).toBeVisible();
  await expect(appearanceStage.locator(".appearance-theme-section").first()).toBeVisible();
  await assertFormFieldsNamed(page, "admin-appearance:panels");

  setPhase("admin-appearance:theme-card-select");
  const inactiveThemeCard = appearanceStage.locator(".admin-theme-card:not(.is-current)").first();
  await expect(inactiveThemeCard).toBeVisible();
  const inactiveThemeKey = await inactiveThemeCard.getAttribute("data-theme-key");
  expect(inactiveThemeKey, "admin-appearance:theme-card-select: theme key").toBeTruthy();
  await clickCardBody(page, inactiveThemeCard, "admin-appearance:theme-card-select");
  const selectedThemeCard = appearanceStage.locator(
    `.admin-theme-card[data-theme-key="${inactiveThemeKey}"]`
  );
  await expect(selectedThemeCard).toHaveClass(/is-current/);

  const defaultThemeCard = appearanceStage.locator(".default-theme-editor");
  await clickCardBody(page, defaultThemeCard, "admin-appearance:default-card-select");
  await expect(defaultThemeCard).toHaveClass(/is-current/);
  await assertFormFieldsNamed(page, "admin-appearance:theme-card-select");

  setPhase("admin-translations:panels");
  const translationsStage = await openAdminSection(page, "translations");
  await expect(translationsStage.locator(".admin-translations-toolbar")).toBeVisible();
  const audienceTabs = translationsStage.locator("[data-admin-translation-audience]");
  await expect
    .poll(async () => audienceTabs.count(), { timeout: 15_000 })
    .toBeGreaterThanOrEqual(3);
  const audienceCount = await audienceTabs.count();
  for (let index = 0; index < audienceCount; index += 1) {
    setPhase(`admin-translations:audience:${index + 1}`);
    await audienceTabs.nth(index).click();
    await expect(audienceTabs.nth(index)).toHaveClass(/is-active/);
  }
  await translationsStage.locator('[data-admin-translation-audience="all"]').click();
  const translationGroup = translationsStage.locator("[data-admin-translation-group]").first();
  await translationGroup.click();
  await expect(translationsStage.locator(".admin-translation-list").first()).toBeVisible();
  const localeToggle = translationsStage.locator("[data-admin-translation-locale]").first();
  await localeToggle.click();
  await expect(localeToggle).toHaveAttribute("aria-expanded", "true");
  await assertFormFieldsNamed(page, "admin-translations:locale-panel");

  setPhase("admin-settings:panels-and-icon-dialog");
  const settingsStage = await openAdminSection(page, "settings");
  await exerciseSettingsDisclosures(settingsStage);
  await assertFormFieldsNamed(page, "admin-settings:panels");
  const iconPickerTrigger = settingsStage.locator(".admin-icon-picker-trigger").first();
  if (await clickFirstVisibleEnabled(iconPickerTrigger)) {
    const iconPickerDialog = page.locator(".dialog-card.admin-icon-picker-dialog");
    await expect(iconPickerDialog).toBeVisible();
    await assertFormFieldsNamed(page, "admin-settings:icon-picker-dialog");
    await closeDialog(iconPickerDialog);
  }

  setPhase("admin-dialog-cleanup");
  await expect(page.locator(".dialog-card:visible")).toHaveCount(0);

  await exerciseActivationSuccessHandoff(page, setPhase);

  setPhase("console-health");
  expect(errors).toEqual([]);
});
