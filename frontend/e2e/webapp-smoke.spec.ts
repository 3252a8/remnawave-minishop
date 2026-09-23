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

/**
 * Horizontal position of the hover drop line, in CSS px inside the overlay.
 * The highlight is painted on a canvas (it clips uPlot's own path), so this
 * samples the axis strip under the plot, where only the dashed line to the
 * readout card is drawn — that line marks the active point.
 */
async function chartHighlightCentre(chart: Locator): Promise<number | null> {
  return chart.locator(".admin-chart-highlight").evaluate((element) => {
    const canvas = element as HTMLCanvasElement;
    const context = canvas.getContext("2d");
    if (!context || !canvas.width || !canvas.height) return null;
    const bandTop = Math.floor(canvas.height * 0.9);
    const bandHeight = canvas.height - bandTop;
    if (bandHeight <= 0) return null;
    const pixels = context.getImageData(0, bandTop, canvas.width, bandHeight).data;
    let total = 0;
    let weighted = 0;
    for (let y = 0; y < bandHeight; y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        const alpha = pixels[(y * canvas.width + x) * 4 + 3];
        if (alpha > 40) {
          total += alpha;
          weighted += x * alpha;
        }
      }
    }
    if (!total) return null;
    const ratio = canvas.width / (canvas.getBoundingClientRect().width || canvas.width);
    return weighted / total / ratio;
  });
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

async function assertCompactReadableTicketBubbles(
  page: Page,
  scope: Locator,
  label: string
): Promise<void> {
  const bubbles = scope.locator(
    ".ticket-message-row--admin .ticket-message-bubble, .ticket-message-row--user .ticket-message-bubble"
  );
  await expect(scope.locator(".ticket-message-row--admin").first()).toBeVisible();
  await expect(scope.locator(".ticket-message-row--user").first()).toBeVisible();
  await expect(bubbles.first()).toBeVisible();
  const expectedTextColor = await page
    .locator("body")
    .evaluate((element) => getComputedStyle(element).color);
  const paint = await bubbles.evaluateAll((elements) =>
    elements.map((element) => {
      const bubbleStyle = getComputedStyle(element);
      const paragraph = element.querySelector(".ticket-message-text p");
      return {
        color: paragraph ? getComputedStyle(paragraph).color : "",
        paddingBottom: Number.parseFloat(bubbleStyle.paddingBottom),
        paddingTop: Number.parseFloat(bubbleStyle.paddingTop),
      };
    })
  );

  expect(paint.length, `${label}-support: conversation bubbles must be rendered`).toBeGreaterThan(
    1
  );
  for (const [index, bubble] of paint.entries()) {
    expect(
      bubble.color,
      `${label}-support: bubble ${index + 1} text must use the theme foreground`
    ).toBe(expectedTextColor);
    expect(
      bubble.paddingTop,
      `${label}-support: bubble ${index + 1} top padding`
    ).toBeLessThanOrEqual(7);
    expect(
      bubble.paddingBottom,
      `${label}-support: bubble ${index + 1} bottom padding`
    ).toBeLessThanOrEqual(7);
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
  await assertCompactReadableTicketBubbles(page, page.locator(".support-ticket-screen"), "webapp");
  const uploadButton = composer.locator(".message-image-dropzone");
  const sendButton = composer.locator(".ticket-composer-send");
  await expect(uploadButton).toContainText("Загрузить файл");
  const actionHeights = await Promise.all([uploadButton.boundingBox(), sendButton.boundingBox()]);
  expect(
    Boolean(
      actionHeights[0] &&
      actionHeights[1] &&
      Math.abs(actionHeights[0].height - actionHeights[1].height) <= 1
    ),
    "webapp-support: upload and send buttons must have the same height"
  ).toBe(true);
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File([new Uint8Array([1, 2, 3])], "dragged-photo.jpg", { type: "image/jpg" })
    );
    window.dispatchEvent(
      new DragEvent("dragenter", { bubbles: true, cancelable: true, dataTransfer: transfer })
    );
  });
  await expect(page.locator(".message-image-drag-overlay")).toBeVisible();
  await page.evaluate(() => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File([new Uint8Array([1, 2, 3])], "dragged-photo.jpg", { type: "image/jpg" })
    );
    window.dispatchEvent(
      new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer })
    );
  });
  await expect(composer.locator(".message-image-preview")).toContainText("dragged-photo.jpg");
  await composer.locator(".message-image-preview button").click();
  const readReceipt = page
    .locator('.support-ticket-screen .ticket-message-receipt[title="Прочитано"]')
    .first();
  await expect(readReceipt).toBeVisible();
  await expect(readReceipt.locator(".lucide-check-check")).toBeVisible();
  const composerInput = composer.locator(".rt-surface .ProseMirror");
  await composerInput.click();
  await composerInput.pressSequentially("Проверка статуса доставки");
  await composer.locator(".ticket-composer-send").click();
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
  await expect
    .poll(() => messageViewport.evaluate((element) => getComputedStyle(element).overflowY))
    .toBe("visible");
  await expect
    .poll(() =>
      page
        .locator(".support-ticket-screen .support-message-scroll")
        .evaluate((element) => element.getBoundingClientRect().height)
    )
    .toBeGreaterThanOrEqual(300);
  await messageViewport.evaluate((element) => {
    element.scrollTop = 0;
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await swipeUp(page, messageViewport, "webapp-support:mobile-scroll");
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  await expect.poll(() => messageViewport.evaluate((element) => element.scrollTop)).toBe(0);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
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
  await assertCompactReadableTicketBubbles(page, supportDialog, "admin");
  const ticketHeader = supportDialog.locator(".support-ticket-header");
  const composerSurface = composer.locator(".rt-surface");
  const composerCounter = composer.locator(".support-admin-composer-counter");
  const composerActions = composer.locator(".support-admin-composer-actions");
  const attachment = composerActions.locator(".message-image-attachment");
  const uploadButton = attachment.locator(".message-image-dropzone");
  const sendButton = composerActions.locator(".admin-btn");

  await page.waitForTimeout(220);
  await expect
    .poll(() => ticketHeader.evaluate((element) => element.getBoundingClientRect().height))
    .toBeLessThan(72);
  const counterInsideSurface = await Promise.all([
    composerSurface.boundingBox(),
    composerCounter.boundingBox(),
  ]).then(([surface, counter]) =>
    Boolean(
      surface &&
      counter &&
      counter.x >= surface.x &&
      counter.y >= surface.y &&
      counter.x + counter.width <= surface.x + surface.width &&
      counter.y + counter.height <= surface.y + surface.height
    )
  );
  expect(counterInsideSurface, "admin-support: counter must stay inside the editor").toBe(true);
  const actionsShareRow = await Promise.all([
    attachment.boundingBox(),
    sendButton.boundingBox(),
  ]).then(([upload, send]) => Boolean(upload && send && Math.abs(upload.y - send.y) <= 4));
  expect(actionsShareRow, "admin-support: image and send actions must share one row").toBe(true);
  await expect(uploadButton).toContainText("Загрузить файл");
  const actionsMatchHeight = await Promise.all([
    uploadButton.boundingBox(),
    sendButton.boundingBox(),
  ]).then(([upload, send]) =>
    Boolean(upload && send && Math.abs(upload.height - send.height) <= 1)
  );
  expect(actionsMatchHeight, "admin-support: image and send actions must match height").toBe(true);
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
  await expect
    .poll(() => messageScroll.evaluate((element) => element.getBoundingClientRect().height))
    .toBeGreaterThanOrEqual(300);
  await expect
    .poll(() => bodyViewport.evaluate((element) => getComputedStyle(element).overflowY))
    .toBe("visible");
  const dialogOverlay = page.locator(".dialog");
  await dialogOverlay.evaluate((element) => {
    element.scrollTop = 0;
  });
  await swipeUp(page, messageScroll, "admin-support:mobile-scroll");
  await expect
    .poll(() => dialogOverlay.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0);
  await expect.poll(() => messageViewport.evaluate((element) => element.scrollTop)).toBe(0);

  const modalCoversHeader = await page.evaluate(() => {
    const header = document.querySelector(".admin-header");
    if (!(header instanceof HTMLElement)) return false;
    const rect = header.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
    return Boolean(hit?.closest(".dialog"));
  });
  expect(modalCoversHeader, "admin-support: modal must stay above the section header").toBe(true);

  await dialogOverlay.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(composer).toBeInViewport();
  await dialogOverlay.evaluate((element) => {
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
  options: { checkBalanceTileSelection?: boolean; checkMobileTariffTapThrough?: boolean } = {}
): Promise<void> {
  const userDialog = page.locator(".dialog-card.admin-user-dialog");
  setPhase(`${phasePrefix}:user-card`);
  await expect(userDialog).toBeVisible();
  await assertFormFieldsNamed(page, `${phasePrefix}:user-card`);
  const remnawaveUserLink = userDialog.locator('[data-admin-action="open-remnawave-user"]');
  await expect(remnawaveUserLink).toBeVisible();
  await expect(remnawaveUserLink).toHaveAttribute(
    "href",
    "https://panel.example.com/dashboard/open/user/77"
  );
  await expect(remnawaveUserLink).toHaveAttribute("target", "_blank");
  await expect(remnawaveUserLink).toHaveAttribute("rel", /noopener/);
  // Subscription, Activity, Notifications, Logs, Actions, Message.
  await exerciseDialogTabs(userDialog, 6, setPhase, `${phasePrefix}:user-tabs`);

  setPhase(`${phasePrefix}:user-avatar`);
  if (
    await clickFirstVisibleEnabled(
      userDialog.locator(".admin-avatar-preview-trigger:not(:disabled)")
    )
  ) {
    const avatarViewer = page.locator("[data-image-viewer]");
    await expect(avatarViewer).toBeVisible();
    await assertFormFieldsNamed(page, `${phasePrefix}:user-avatar`);
    await expect(avatarViewer.locator(".image-viewer-scale")).toHaveText("100%");
    await avatarViewer.locator('[data-image-viewer-action="zoom-in"]').click();
    await expect(avatarViewer.locator(".image-viewer-scale")).toHaveText("125%");
    await avatarViewer.locator('[data-image-viewer-action="close"]').click();
    await expect(avatarViewer).toBeHidden();
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

  if (options.checkBalanceTileSelection) {
    setPhase(`${phasePrefix}:balance-tile-selection`);
    const balanceCard = actionsPanel.locator(".admin-user-action-sheet--balance");
    const mainBalanceTile = balanceCard.locator(".balance-summary-tile").nth(0);
    const partnerBalanceTile = balanceCard.locator(".balance-summary-tile").nth(1);
    const targetTrigger = balanceCard.locator(".balance-target-field .admin-select-trigger");
    await expect(mainBalanceTile).toHaveAttribute("aria-pressed", "true");
    await expect(partnerBalanceTile).toBeEnabled();
    await partnerBalanceTile.click();
    await expect(partnerBalanceTile).toHaveAttribute("aria-pressed", "true");
    await expect(mainBalanceTile).toHaveAttribute("aria-pressed", "false");
    await expect(targetTrigger).toContainText("Партнёрский баланс");
    await mainBalanceTile.click();
    await expect(mainBalanceTile).toHaveAttribute("aria-pressed", "true");
    await expect(targetTrigger).toContainText("Основной баланс");
  }

  if (options.checkMobileTariffTapThrough) {
    setPhase(`${phasePrefix}:mobile-extend-tariff-select`);
    await assertMobileExtendTariffSelectDoesNotTapThrough(
      page,
      userDialog,
      `${phasePrefix}:mobile-extend-tariff-select`
    );
  }

  setPhase(`${phasePrefix}:message-composer`);
  // Messaging one customer moved out of the actions sheet into its own tab,
  // where the shared composer carries channels and buttons.
  // bits-ui renders the trigger's value as `data-value`, and the demo runs in
  // Russian, so neither the label text nor a `value` attribute identifies it.
  await userDialog.locator('.admin-tabs-trigger[data-value="message"]').first().click();
  const composerCard = userDialog.locator(".admin-user-action-sheet--message");
  await expect(composerCard).toBeVisible();
  await expect(composerCard.locator(".ProseMirror")).toBeVisible();
  await expect(composerCard.locator('[data-admin-action="send-user-message"]')).toBeDisabled();
  await assertFormFieldsNamed(page, `${phasePrefix}:message-composer`);
  await userDialog.locator('.admin-tabs-trigger[data-value="actions"]').first().click();
  await expect(actionsPanel).toBeVisible();

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
  const sectionTriggers = stage.locator(
    ".admin-accordion > .admin-accordion-item > .admin-accordion-trigger"
  );
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
      await expect(confirmDialog.locator(".dialog-close-button")).toHaveCount(0);
      await confirmDialog.getByRole("button", { name: "Отмена", exact: true }).click();
      await expect(confirmDialog).toBeHidden();
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
    await expect(deviceDisconnectDialog.locator(".dialog-close-button")).toHaveCount(0);
    await deviceDisconnectDialog.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(deviceDisconnectDialog).toBeHidden();
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

test("support ticket conversations stay readable and scroll on desktop and mobile", async ({
  page,
}) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(`${APP_URL}?theme_preview=light`);
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

test("balance top-up dialog uses the demo viewport without an idle scrollbar", async ({ page }) => {
  await page.setViewportSize({ width: 583, height: 520 });
  await page.goto(`${APP_URL}?path=/home&mock=user-balance`);

  await page.locator('[data-webapp-action="open-balance-topup"]').click();
  const dialog = page.locator(".dialog-card.balance-topup-dialog");
  const viewport = dialog.locator(".dialog-body-scroll > .scroll-area__viewport");
  const scrollbar = dialog.locator('.scroll-area__scrollbar[data-orientation="vertical"]');

  await expect(dialog).toBeVisible();
  await expect
    .poll(() => viewport.evaluate((element) => element.scrollHeight - element.clientHeight))
    .toBeLessThanOrEqual(1);
  await expect(scrollbar).toHaveCount(0);
});

test("optional home widgets stay disabled by default and use dedicated presets", async ({
  page,
}) => {
  await page.goto(`${APP_URL}?path=/home&mock=tariffs`);
  await expect(page.locator(".home-compact-summary")).toHaveCount(0);
  await expect(page.locator(".home-balance-card")).toHaveCount(0);
  await expect(page.locator(".server-status-card")).toHaveCount(0);

  await page.goto(`${APP_URL}?path=/home&mock=compact`);
  await expect(page.locator(".home-compact-summary")).toBeVisible();
  await expect(page.locator(".compact-balance")).toHaveCount(0);
  await expect(page.locator(".server-status-card")).toHaveCount(0);
  const regularTrafficRow = page.locator(".compact-traffic-item").first();
  await expect(regularTrafficRow.locator(".compact-traffic-label")).not.toContainText("13.10.2026");
  await regularTrafficRow.locator('[data-webapp-action="open-regular-traffic-help"]').click();
  await expect(page.locator("#compact-regular-traffic-help")).toContainText("13.10.2026");

  await page.goto(`${APP_URL}?path=/home&mock=server-status`);
  await expect(page.locator(".server-status-card")).toBeVisible();
  await expect(page.locator(".home-compact-summary")).toHaveCount(0);
  await expect(page.locator(".home-balance-card")).toHaveCount(0);
});

test("device traffic bonuses stay legible on mobile", async ({ page }) => {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await page.goto(`${APP_URL}?mock=devices`);
  const nav = page.locator("nav.bottom-nav");
  await expect(nav).toBeVisible();
  await nav.getByRole("button", { name: "Устройства", exact: true }).click();

  const openTopup = webappAction(page, "open-device-topup");
  await expect(openTopup).toBeVisible();
  await openTopup.click();

  const dialog = page.locator(".dialog-card.webapp-device-topup-dialog");
  await expect(dialog).toBeVisible();
  await expect(
    dialog.locator(".hwid-traffic-bonus", {
      hasText: "Плюс 15 ГБ к месячному трафику",
    })
  ).toBeVisible();
  await expect(
    dialog.locator(".hwid-traffic-bonus", {
      hasText: "Плюс 45 ГБ к месячному трафику",
    })
  ).toBeVisible();
});

test("a theme can collapse the referral bonus list", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);

  await page.goto("/demo/runtime/invite?theme_preview=dark");
  await expect(page.locator(".referral-bonus-row").first()).toBeVisible();
  await expect(page.locator(".referral-bonus-disclosure")).toHaveCount(0);

  await page.goto("/demo/runtime/invite?theme_preview=ascii");
  const disclosure = page.locator(".referral-bonus-disclosure");
  const trigger = disclosure.locator(".referral-bonus-summary");
  await expect(disclosure).toHaveCount(1);
  await expect(trigger).toContainText("Бонус зависит от тарифа и периода оплаты друга");
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(page.locator(".referral-tariff-dropdown")).toHaveCount(0);
  await expect(page.locator(".referral-bonus-row-nested")).toHaveCount(0);

  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(".referral-tariff-dropdown")).toHaveCount(2);
  await expect(page.locator(".referral-tariff-summary").first()).toBeVisible();
  await expect(page.locator(".referral-bonus-row-nested")).toHaveCount(4);
  await expect(page.locator(".referral-bonus-row-nested").first()).toBeHidden();

  await page.locator(".referral-tariff-summary").first().click();
  await expect(page.locator(".referral-bonus-row-nested").first()).toBeVisible();
});

test("Telegram fullscreen fallback protects webapp actions and admin chrome", async ({ page }) => {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await page.addInitScript(() => {
    Object.assign(window, {
      Telegram: {
        WebApp: {
          expand() {},
          initData: "",
          isFullscreen: false,
          isVersionAtLeast: () => true,
          offEvent() {},
          onEvent() {},
          platform: "ios",
          ready() {},
          requestFullscreen() {},
        },
      },
    });
  });
  await page.goto(APP_URL);
  const applyTelegramFullscreenInsets = () => {
    const style = document.documentElement.style;
    style.setProperty("--tg-content-safe-area-inset-top", "0px");
    style.setProperty("--tg-content-safe-area-inset-bottom", "34px");
  };
  await page.evaluate(applyTelegramFullscreenInsets);
  await expect(page.locator("html")).toHaveAttribute("data-telegram-fullscreen-requested", "true");

  const phoneScreen = page.locator(".phone-screen");
  const bottomNav = page.locator("nav.bottom-nav");
  const renewalAction = webappAction(page, "open-payment");
  await expect(bottomNav).toBeVisible();
  await expect(renewalAction).toBeVisible();

  const homeInsets = await phoneScreen.evaluate((element) => {
    const phoneStyle = window.getComputedStyle(element);
    const homeStyle = window.getComputedStyle(document.querySelector(".home-layout")!);
    const navStyle = window.getComputedStyle(document.querySelector("nav.bottom-nav")!);
    return {
      top: Number.parseFloat(phoneStyle.paddingTop),
      bottom: Number.parseFloat(phoneStyle.paddingBottom),
      homeClearance: Number.parseFloat(homeStyle.paddingBottom),
      navBottom: Number.parseFloat(navStyle.bottom),
    };
  });
  expect(homeInsets.top).toBeLessThan(96);
  expect(homeInsets.bottom).toBeGreaterThanOrEqual(34);
  expect(homeInsets.homeClearance).toBeGreaterThanOrEqual(110);
  expect(homeInsets.navBottom).toBeGreaterThanOrEqual(34);

  await renewalAction.click();
  const webappDialog = page.locator(".dialog:has(.webapp-payment-dialog)");
  const webappDialogCard = webappDialog.locator(".webapp-payment-dialog");
  await expect(webappDialogCard).toBeVisible();
  const webappDialogGeometry = await webappDialog.evaluate((element) => ({
    paddingTop: Number.parseFloat(window.getComputedStyle(element).paddingTop),
    cardTop: element.querySelector(".dialog-card")!.getBoundingClientRect().top,
  }));
  expect(webappDialogGeometry.paddingTop).toBeGreaterThanOrEqual(96);
  expect(webappDialogGeometry.cardTop).toBeGreaterThanOrEqual(96);
  await closeDialog(webappDialogCard);

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await expect
    .poll(async () => {
      const actionBox = await renewalAction.boundingBox();
      const navBox = await bottomNav.boundingBox();
      if (!actionBox || !navBox) return -1;
      return navBox.y - (actionBox.y + actionBox.height);
    })
    .toBeGreaterThanOrEqual(20);

  await bottomNav.getByRole("button", { name: "Настройки", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page).toHaveURL(/\/demo\/runtime\/settings/);
  const appHeader = page.locator(".phone-screen > .app-header");
  await expect(appHeader).toBeVisible();
  const customerHeaderTop = await appHeader.evaluate(
    (element) => element.getBoundingClientRect().top
  );
  expect(customerHeaderTop).toBeGreaterThanOrEqual(96);

  await page.goto("/demo/runtime/admin/stats?theme_preview=dark");
  await page.evaluate(applyTelegramFullscreenInsets);
  const adminHeader = page.locator(".admin-header");
  await expect(adminHeader).toBeVisible();
  const adminGeometry = await page.locator(".admin-screen-wrap").evaluate((element) => ({
    paddingTop: Number.parseFloat(window.getComputedStyle(element).paddingTop),
    headerTop: document.querySelector(".admin-header")!.getBoundingClientRect().top,
  }));
  expect(adminGeometry.paddingTop).toBeGreaterThanOrEqual(96);
  expect(adminGeometry.headerTop).toBeGreaterThanOrEqual(96);

  await page.goto("/demo/runtime/admin/users?theme_preview=dark");
  await page.evaluate(applyTelegramFullscreenInsets);
  await page.locator(".admin-user-mobile-card").first().click();
  const userDialog = page.locator(".dialog:has(.admin-user-dialog)");
  const userDialogCard = userDialog.locator(".admin-user-dialog");
  await expect(userDialogCard).toBeVisible();
  const adminDialogGeometry = await userDialog.evaluate((element) => ({
    paddingTop: Number.parseFloat(window.getComputedStyle(element).paddingTop),
    cardTop: element.querySelector(".dialog-card")!.getBoundingClientRect().top,
  }));
  expect(adminDialogGeometry.paddingTop).toBeGreaterThanOrEqual(96);
  expect(adminDialogGeometry.cardTop).toBeGreaterThanOrEqual(96);

  const avatarTrigger = userDialogCard.locator(".admin-avatar-preview-trigger:not(:disabled)");
  await expect(avatarTrigger).toBeVisible();
  await avatarTrigger.click();
  const imageViewer = page.locator("[data-image-viewer]");
  const imageViewerPanel = imageViewer.locator(".image-viewer-panel");
  await expect(imageViewerPanel).toBeVisible();
  const imageViewerGeometry = await imageViewerPanel.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { top: rect.top, bottom: rect.bottom, viewportHeight: window.innerHeight };
  });
  expect(imageViewerGeometry.top).toBeGreaterThanOrEqual(96);
  expect(imageViewerGeometry.bottom).toBeLessThanOrEqual(imageViewerGeometry.viewportHeight - 34);
  await imageViewer.locator('[data-image-viewer-action="close"]').click();
  await closeDialog(userDialogCard);
});

test("partner operations open their linked payment card", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(
    "/demo/runtime/admin/partners/partner/PT-104?partner_admin_scenario=populated&theme_preview=dark"
  );

  await page.getByRole("tab", { name: "Операции", exact: true }).click();
  const activity = page.locator(".partners-detail-tabs");
  await expect(activity.locator("tbody")).toContainText("LG-903");

  const commission = activity
    .locator(".admin-entity-link.is-actionable")
    .filter({ hasText: "COM-184" })
    .first();
  await expect(commission).toBeVisible();
  await commission.click();

  const paymentDialog = page.locator(".dialog-card.admin-payment-dialog");
  await expect(paymentDialog).toBeVisible();
  await expect(paymentDialog).toContainText("Платёж #710024");
  await closeDialog(paymentDialog);
});

test("partner admin tabs keep stable routes and share the users page size", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(
    "/demo/runtime/admin/partners/applications?partner_admin_scenario=populated&theme_preview=dark"
  );

  const partnerPage = page.locator(".partners-admin-page");
  await expect(partnerPage.getByRole("tab", { name: /Заявки/ })).toHaveAttribute(
    "data-state",
    "active"
  );
  await expect(partnerPage.locator("tbody tr")).toHaveCount(4);
  await expect(partnerPage.locator("tbody .admin-entity-link.is-person img")).toHaveCount(4);

  await partnerPage.getByRole("tab", { name: "Партнёры", exact: true }).click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/partners\/partners\?/);
  await expect(partnerPage.locator("tbody tr")).toHaveCount(6);
  await expect(partnerPage.locator("tbody .admin-entity-link.is-person img")).toHaveCount(6);

  await partnerPage.getByRole("tab", { name: /Выводы/ }).click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/partners\/withdrawals\?/);
  await expect(partnerPage.locator("tbody tr")).toHaveCount(6);
  await expect(partnerPage.locator("tbody .admin-entity-link.is-person img")).toHaveCount(6);

  await page.goBack();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/partners\/partners\?/);
  await expect(partnerPage.getByRole("tab", { name: "Партнёры", exact: true })).toHaveAttribute(
    "data-state",
    "active"
  );

  await adminSectionButton(page, "stats").click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/stats\?/);
  await adminSectionButton(page, "partners").click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/partners\?/);
  await expect(partnerPage.getByRole("tab", { name: "Сводка", exact: true })).toHaveAttribute(
    "data-state",
    "active"
  );
});

test("partner dashboard converts referrals when the referral system is disabled", async ({
  page,
}) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(
    "/demo/runtime/admin/partners?partner_admin_scenario=populated&theme_preview=dark"
  );
  await expect(page.locator(".partners-referral-import-banner")).toHaveCount(0);

  await page.goto(
    "/demo/runtime/admin/partners?partner_admin_scenario=populated&mock=partner-referral-disabled&theme_preview=dark"
  );
  const banner = page.locator(".partners-referral-import-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText(/12\s+пользователей к конвертации/);

  await banner.getByRole("button", { name: "Конвертировать рефералов", exact: true }).click();
  const dialog = page.locator(".dialog-card.admin-partners-dialog");
  await expect(dialog).toContainText("Конвертировать всех доступных рефералов?");
  await expect(dialog).toContainText("У найденных рефералов исторических платежей: 9");
  await dialog.getByRole("button", { name: "Подтвердить", exact: true }).click();

  await expect(dialog).toBeHidden();
  await expect(banner).toContainText("Конвертировано пользователей: 12");
  await expect(banner).toContainText("Все доступные рефералы уже являются клиентами");
});

test("program entries follow the enabled feature combination", async ({ page }) => {
  await page.goto("/demo/runtime/invite?mock=partner-referral-disabled&theme_preview=dark");

  let bottomNav = page.locator(".bottom-nav");
  const partnerNavEntry = bottomNav.locator('[data-nav-level="primary"][aria-label="Партнёрка"]');
  await expect(partnerNavEntry).toBeVisible();
  await expect(bottomNav.locator('[data-nav-level="primary"][aria-label="Бонусы"]')).toBeVisible();
  await expect(page.locator(".gift-entry")).toBeVisible();
  await expect(partnerNavEntry.locator("svg path").first()).toHaveAttribute(
    "d",
    "m11 17 2 2a1 1 0 1 0 3-3"
  );
  await expect(page.locator(".referral-program-shell")).toHaveCount(0);
  await expect(page.locator(".promo-code-input")).toBeEditable();

  await partnerNavEntry.click();
  await expect(page).toHaveURL(/\/demo\/runtime\/partner\?/);
  await expect(partnerNavEntry).toHaveClass(/active/);
  await expect(page.locator(".partner-back")).toHaveCount(0);

  await bottomNav.getByRole("button", { name: "Настройки", exact: true }).click();
  await expect(page.locator(".promo-code-input")).toBeEditable();
  await expect(page.locator('[data-webapp-action="open-partner-program"]')).toHaveCount(0);

  await page.goto("/demo/runtime/settings?mock=partner-referral-enabled&theme_preview=dark");

  bottomNav = page.locator(".bottom-nav");
  await expect(bottomNav.locator('[data-nav-level="primary"][aria-label="Бонусы"]')).toBeVisible();
  await expect(bottomNav.locator('[data-nav-level="primary"][aria-label="Партнёрка"]')).toHaveCount(
    0
  );
  await expect(
    bottomNav.locator(".rail-settings-subnav").getByRole("button", {
      name: "Партнёрка",
      exact: true,
    })
  ).toBeVisible();
  await expect(page.locator(".promo-code-input")).toHaveCount(0);
  const partnerSettingsEntry = page.locator('[data-webapp-action="open-partner-program"]');
  await expect(partnerSettingsEntry).toBeVisible();
  await expect(partnerSettingsEntry.locator("svg path").first()).toHaveAttribute(
    "d",
    "m11 17 2 2a1 1 0 1 0 3-3"
  );

  await partnerSettingsEntry.click();
  await expect(page).toHaveURL(/\/demo\/runtime\/partner\?/);
  await expect(bottomNav.locator('[data-nav-level="primary"][aria-label="Настройки"]')).toHaveClass(
    /active/
  );
  await expect(
    bottomNav.locator(".rail-settings-subnav").getByRole("button", {
      name: "Партнёрка",
      exact: true,
    })
  ).toHaveClass(/active/);

  const partnerBack = page.locator(".partner-back");
  await expect(partnerBack).toBeVisible();
  await expect(partnerBack).toContainText("Назад");
  await partnerBack.click();
  await expect(page).toHaveURL(/\/demo\/runtime\/settings\?/);
});

test("partner encryption diagnostic explains safe initial key setup", async ({ page }) => {
  await page.goto(
    "/demo/runtime/admin/settings/partner?partner_settings_scenario=missing_key&theme_preview=dark"
  );

  const diagnostic = page.locator(".partner-diagnostics .danger").filter({
    hasText: "Ключ шифрования реквизитов не задан",
  });
  await expect(diagnostic).toBeVisible();
  await expect(diagnostic.locator("[data-partner-encryption-command]")).toHaveText(
    "openssl rand -base64 32 | tr '+/' '-_'"
  );
  const diagnosticCards = page.locator(".partner-diagnostics > div");
  await expect(diagnosticCards).toHaveCount(2);
  const cardGeometry = await diagnosticCards.evaluateAll((cards) =>
    cards.map((card) => {
      const rect = card.getBoundingClientRect();
      return { bottom: rect.bottom, top: rect.top, width: rect.width };
    })
  );
  expect(Math.abs(cardGeometry[0].width - cardGeometry[1].width)).toBeLessThanOrEqual(1);
  expect(cardGeometry[1].top).toBeGreaterThan(cardGeometry[0].bottom);
  await expect(diagnostic).toContainText("PARTNER_REQUISITES_ENCRYPTION_KEY");
  await expect(diagnostic).toContainText("перезапустите backend и worker");
  await expect(diagnostic).toContainText("никогда не сохраняйте секрет в Git");

  await page.goto(
    "/demo/runtime/admin/settings/partner?partner_settings_scenario=program_on&theme_preview=dark"
  );
  await expect(page.locator("[data-partner-encryption-command]")).toHaveCount(0);
});

test("partner withdrawal method actions stay clear of section copy", async ({ page }) => {
  const route =
    "/demo/runtime/admin/settings/partner?partner_settings_scenario=program_on&theme_preview=dark";

  await page.setViewportSize(MOBILE_VIEWPORT);
  await page.goto(route);
  const section = page.locator(".partner-methods-section");
  const mobileGeometry = await section.evaluate((element) => {
    const copy = element.querySelector<HTMLElement>(".admin-settings-field-group-head-copy");
    const actions = element.querySelector<HTMLElement>(".partner-method-add");
    if (!copy || !actions) throw new Error("Partner withdrawal method header is incomplete");
    const copyRect = copy.getBoundingClientRect();
    const actionsRect = actions.getBoundingClientRect();
    return {
      actionsTop: actionsRect.top,
      actionsWidth: actionsRect.width,
      buttonWidths: Array.from(
        actions.querySelectorAll<HTMLElement>(".admin-btn"),
        (button) => button.getBoundingClientRect().width
      ),
      copyBottom: copyRect.bottom,
      copyWidth: copyRect.width,
    };
  });
  expect(mobileGeometry.actionsTop).toBeGreaterThan(mobileGeometry.copyBottom + 10);
  expect(Math.abs(mobileGeometry.actionsWidth - mobileGeometry.copyWidth)).toBeLessThanOrEqual(1);
  expect(mobileGeometry.buttonWidths).toHaveLength(3);
  for (const width of mobileGeometry.buttonWidths) {
    expect(Math.abs(width - mobileGeometry.actionsWidth)).toBeLessThanOrEqual(1);
  }

  await page.setViewportSize(DESKTOP_VIEWPORT);
  const desktopGeometry = await section.evaluate((element) => {
    const copy = element.querySelector<HTMLElement>(".admin-settings-field-group-head-copy");
    const actions = element.querySelector<HTMLElement>(".partner-method-add");
    if (!copy || !actions) throw new Error("Partner withdrawal method header is incomplete");
    const copyRect = copy.getBoundingClientRect();
    const actionsRect = actions.getBoundingClientRect();
    return { actionsLeft: actionsRect.left, copyRight: copyRect.right };
  });
  expect(desktopGeometry.actionsLeft).toBeGreaterThanOrEqual(desktopGeometry.copyRight + 10);
});

test("partner automatic enrollment requires confirmation", async ({ page }) => {
  await page.goto(
    "/demo/runtime/admin/settings/partner?partner_settings_scenario=program_on&theme_preview=dark"
  );

  const setting = page.locator(".admin-setting").filter({
    hasText: "Автоматически подключать всех пользователей",
  });
  const toggle = setting.getByRole("switch");
  await expect(toggle).not.toBeChecked();
  await toggle.click();

  const dialog = page.getByRole("dialog", {
    name: "Включить автоматическое подключение?",
  });
  await expect(dialog).toContainText("для каждого подходящего пользователя");
  await dialog.getByRole("button", { name: "Подтвердить" }).click();
  await expect(toggle).toBeChecked();
});

test("partner account stays compact, table-driven, and keeps the tour ring local", async ({
  page,
}) => {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await page.goto("/demo/runtime/partner?partner_scenario=active_populated&theme_preview=dark");

  const overview = page.locator(".partner-overview-card");
  await expect(overview.locator(".partner-overview-head")).toContainText("Партнёрский кабинет");
  await expect(overview.locator(".partner-link-item")).toHaveCount(2);
  await expect(overview.getByRole("button", { name: "Поделиться" })).toHaveCount(0);
  await expect(overview.getByRole("button", { name: "Открыть QR-код" })).toHaveCount(0);
  await expect(overview.locator(".partner-link-item code")).toHaveText([
    "https://t.me/minishop_bot?start=p_Q7m2pK8v4",
    "https://example.com/?start=p_Q7m2pK8v4",
  ]);
  await expect(page.locator(".partner-balance-card .partner-section-head")).toContainText(
    "Баланс и вывод"
  );
  const statistics = page.locator(".partner-stats-card");
  await expect(statistics.locator(".partner-section-head")).toContainText("Партнёрская статистика");
  await expect(statistics).not.toContainText("Детали партнёрской программы");
  await expect(page.locator(".partner-methods-section, .partner-methods")).toHaveCount(0);
  await expect(statistics.locator(".partner-data-table tbody tr")).toHaveCount(20);
  const pagination = statistics.locator(".admin-pagination");
  await expect(pagination).toContainText("Страница 1 из 2");
  await expect(pagination).toContainText("Всего 21");

  await pagination.getByRole("button", { name: "Далее", exact: true }).click();
  await expect(statistics.locator(".partner-data-table tbody tr")).toHaveCount(1);
  await expect(statistics.locator(".partner-data-table tbody tr").first()).toContainText(
    "Demo client 17"
  );
  await expect(pagination).toContainText("Страница 2 из 2");
  await pagination.getByRole("button", { name: "Назад", exact: true }).click();

  await page.getByRole("button", { name: "Вывести", exact: true }).click();
  const withdrawalDialog = page.locator(".dialog-card.partner-withdraw-dialog");
  await expect(withdrawalDialog).toBeVisible();
  await expect(withdrawalDialog.locator(".partner-method-options button")).toHaveCount(3);
  await withdrawalDialog
    .locator(".partner-method-options button")
    .filter({ hasText: "Криптовалюта" })
    .click();
  const networkTrigger = withdrawalDialog.locator(".partner-network-select-trigger");
  await networkTrigger.click();
  const networkOptions = page.locator(".partner-network-select-item");
  await expect(networkOptions).toHaveCount(2);
  const networkTypography = await networkOptions.evaluateAll((options) =>
    options.map((option) => {
      const style = window.getComputedStyle(option);
      return [style.fontFamily, style.fontSize, style.fontWeight, style.lineHeight].join("|");
    })
  );
  expect(new Set(networkTypography).size).toBe(1);
  const triggerTypography = await networkTrigger.evaluate((element) => {
    const style = window.getComputedStyle(element);
    return [style.fontFamily, style.fontSize, style.fontWeight, style.lineHeight].join("|");
  });
  expect(networkTypography[0]).toBe(triggerTypography);
  await page.keyboard.press("Escape");
  await expect(page.locator(".partner-network-select-content")).toBeHidden();
  await page.keyboard.press("Escape");
  await expect(withdrawalDialog).toBeHidden();

  const firstLink = overview.locator(".partner-link-item").first();
  const linkField = firstLink.locator("code");
  const copyButton = firstLink.locator(".partner-copy-button");
  const [fieldBox, copyBox] = await Promise.all([
    linkField.boundingBox(),
    copyButton.boundingBox(),
  ]);
  expect(fieldBox).not.toBeNull();
  expect(copyBox).not.toBeNull();
  expect(Math.abs(copyBox!.y - fieldBox!.y)).toBeLessThan(2);
  expect(copyBox!.x).toBeGreaterThan(fieldBox!.x);
  expect(fieldBox!.x + fieldBox!.width).toBeLessThanOrEqual(copyBox!.x + 1);

  const firstTableRow = statistics.locator(".partner-data-table tbody tr").first();
  await expect(firstTableRow).toHaveCSS("display", "block");
  await statistics.getByRole("tab", { name: /Комиссии/ }).click();
  await expect(statistics.locator(".partner-data-table tbody tr")).toHaveCount(20);
  await expect(statistics.locator(".partner-data-table thead th")).toHaveCount(5);
  const reversedCommission = statistics.locator(".partner-status-tooltip-trigger").first();
  await expect(reversedCommission).toContainText("Отменена");
  await reversedCommission.hover();
  await expect(page.locator(".partner-status-tooltip-content")).toContainText(
    "Начисление отменено, потому что платёж клиента был возвращён или аннулирован."
  );
  await pagination.getByRole("button", { name: "Далее", exact: true }).click();
  await expect(statistics.locator(".partner-data-table tbody tr")).toHaveCount(1);
  await expect(statistics.locator(".partner-data-table tbody tr").first()).toContainText(
    "Demo client 17"
  );
  await pagination.getByRole("button", { name: "Назад", exact: true }).click();
  await statistics.getByRole("tab", { name: /Выводы/ }).click();
  await expect(statistics.locator(".partner-data-table tbody tr")).toHaveCount(20);
  await expect(statistics.locator(".partner-data-table thead th")).toHaveCount(5);
  await pagination.getByRole("button", { name: "Далее", exact: true }).click();
  await expect(statistics.locator(".partner-data-table tbody tr")).toHaveCount(1);
  await expect(statistics.locator(".partner-data-table tbody tr").first()).toContainText("WD-D17");
  await pagination.getByRole("button", { name: "Назад", exact: true }).click();

  await page.getByRole("button", { name: "Как это работает", exact: true }).click();
  const spotlight = page.locator(".partner-tour-spotlight.is-ready");
  await expect(spotlight).toBeVisible();
  const spotlightPaint = await spotlight.evaluate((element) => {
    const box = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    const ring = window.getComputedStyle(element, "::after");
    return {
      boxWidth: box.width,
      viewportWidth: window.innerWidth,
      shadow: style.boxShadow,
      transitionDuration: style.transitionDuration,
      ringBorderWidth: ring.borderTopWidth,
      ringOpacity: ring.opacity,
    };
  });
  expect(spotlightPaint.boxWidth).toBeLessThan(spotlightPaint.viewportWidth - 24);
  expect(spotlightPaint.shadow).toContain("9999px");
  expect(spotlightPaint.transitionDuration).toBe("0s");
  expect(spotlightPaint.ringBorderWidth).toBe("2px");
  expect(spotlightPaint.ringOpacity).toBe("1");

  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto("/demo/runtime/partner?partner_scenario=active_populated&theme_preview=dark");
  await expect(page.locator(".partner-copy-button").first()).toBeVisible();
  const desktopStatistics = page.locator(".partner-stats-card");
  await expect(desktopStatistics.locator(".partner-table-primary").first()).toContainText(
    "Alex M."
  );
  await desktopStatistics.getByRole("button", { name: "Оборот", exact: true }).click();
  await expect(desktopStatistics.locator(".partner-table-primary").first()).toContainText(
    "Demo client 17"
  );
  const desktopLayout = await page.evaluate(() => {
    const copyButton = document.querySelector<HTMLElement>(".partner-copy-button");
    return {
      viewportWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      copyRight: copyButton?.getBoundingClientRect().right ?? 0,
    };
  });
  expect(desktopLayout.scrollWidth).toBeLessThanOrEqual(desktopLayout.viewportWidth);
  expect(desktopLayout.copyRight).toBeLessThanOrEqual(desktopLayout.viewportWidth);
});

test("partner loading and empty chart states preserve their final geometry", async ({ page }) => {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await page.goto("/demo/runtime/partner?partner_scenario=loading&theme_preview=dark");

  const accountSkeleton = page.locator(".partner-skeleton");
  await expect(accountSkeleton.locator(".partner-skeleton-card")).toHaveCount(3);
  await expect(accountSkeleton.locator(".partner-skeleton-table-row")).toHaveCount(4);
  const mobileFit = await page.evaluate(() => {
    const card = document.querySelector<HTMLElement>(".partner-skeleton-card");
    const button = document.querySelector<HTMLElement>(
      ".partner-overview-head > .partner-skeleton-button"
    );
    return {
      buttonRight: button?.getBoundingClientRect().right ?? 0,
      cardRight: card?.getBoundingClientRect().right ?? 0,
      scrollWidth: document.documentElement.scrollWidth,
      viewportWidth: window.innerWidth,
    };
  });
  expect(mobileFit.buttonRight).toBeLessThanOrEqual(mobileFit.cardRight);
  expect(mobileFit.scrollWidth).toBeLessThanOrEqual(mobileFit.viewportWidth);

  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto("/demo/runtime/admin/partners?partner_admin_scenario=loading&theme_preview=dark");
  const adminSkeleton = page.locator(".partners-skeleton");
  await expect(adminSkeleton.locator(".partners-kpi-card")).toHaveCount(8);
  await expect(
    adminSkeleton.locator(".partners-chart-block .admin-revenue-chart-body")
  ).toHaveCount(2);
  await expect(adminSkeleton.locator(".partners-preview-card")).toHaveCount(3);
  const skeletonKpiHeight = await adminSkeleton
    .locator(".partners-kpi-card")
    .first()
    .evaluate((element) => element.getBoundingClientRect().height);
  const skeletonChartHeight = await adminSkeleton
    .locator(".partners-chart-block .admin-revenue-svg-frame")
    .first()
    .evaluate((element) => element.getBoundingClientRect().height);

  await page.goto(
    "/demo/runtime/admin/partners?partner_admin_scenario=populated&theme_preview=dark"
  );
  const partnerDashboard = page.locator(".partners-admin-page");
  const finalKpiHeight = await partnerDashboard
    .locator(".partners-kpi-card")
    .first()
    .evaluate((element) => element.getBoundingClientRect().height);
  const finalChartHeight = await partnerDashboard
    .locator(".partners-chart-block .admin-revenue-svg-frame")
    .first()
    .evaluate((element) => element.getBoundingClientRect().height);
  expect(Math.abs(skeletonKpiHeight - finalKpiHeight)).toBeLessThanOrEqual(12);
  expect(Math.abs(skeletonChartHeight - finalChartHeight)).toBeLessThanOrEqual(1);

  await page.goto(
    "/demo/runtime/admin/partners?partner_admin_scenario=empty_charts&theme_preview=dark"
  );
  const emptyPartnerCharts = page.locator(".partners-chart-block .admin-chart-empty");
  await expect(emptyPartnerCharts).toHaveCount(2);
  await expect(emptyPartnerCharts).toHaveText(["Нет данных для графика", "Нет данных для графика"]);
  const emptyPartnerChartHeight = await emptyPartnerCharts
    .first()
    .locator("..")
    .evaluate((element) => element.getBoundingClientRect().height);
  expect(Math.abs(emptyPartnerChartHeight - finalChartHeight)).toBeLessThanOrEqual(1);

  await page.goto(
    "/demo/runtime/admin/partners?partner_admin_scenario=empty_lists&theme_preview=dark"
  );
  const emptyDashboardTables = page.locator(".partners-dashboard-table-card > .admin-chart-empty");
  await expect(emptyDashboardTables).toHaveCount(2);
  await expect(emptyDashboardTables).toHaveText(["Заявок на вывод пока нет", "Партнёров пока нет"]);

  await page.goto("/demo/runtime/admin/stats?stats_scenario=empty_revenue&theme_preview=dark");
  const emptyRevenueChart = page.locator(".admin-revenue-chart .admin-chart-empty");
  await expect(emptyRevenueChart).toHaveText("Нет данных для графика");
  await expect(page.locator(".admin-revenue-chart .admin-revenue-chart-body")).toHaveCount(0);
});

test("admin charts reveal on entry, morph between ranges, and respect reduced motion", async ({
  page,
}) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  const revenueChart = page.locator(".admin-revenue-chart-body");
  await Promise.all([
    page.goto("/demo/runtime/admin/stats?theme_preview=dark"),
    // A cold admin bundle can take longer than Playwright's default assertion timeout.
    expect(revenueChart).toHaveAttribute("data-chart-motion", "reveal", { timeout: 20_000 }),
  ]);
  await revenueChart.locator(".u-over").hover();
  await expect(revenueChart).toHaveAttribute("data-chart-motion", "idle", { timeout: 2_000 });
  await expect(revenueChart.locator(".admin-chart-tooltip.is-visible")).toBeVisible();

  await page.getByRole("tab", { name: "30 дн.", exact: true }).click();
  await expect(revenueChart).toHaveAttribute("data-chart-motion", "morph");
  const chartGeometryFrames = [];
  for (let frame = 0; frame < 12; frame += 1) {
    chartGeometryFrames.push(
      await revenueChart.evaluate((element) => {
        const over = element.querySelector<HTMLElement>(".u-over")?.getBoundingClientRect();
        const axes = element.querySelectorAll<HTMLElement>(".u-axis");
        return {
          height: over?.height ?? 0,
          left: over?.left ?? 0,
          top: over?.top ?? 0,
          width: over?.width ?? 0,
          xTop: axes[0]?.getBoundingClientRect().top ?? 0,
          yLeft: axes[1]?.getBoundingClientRect().left ?? 0,
        };
      })
    );
    await page.waitForTimeout(20);
  }
  for (const key of ["height", "left", "top", "width", "xTop", "yLeft"] as const) {
    const values = chartGeometryFrames.map((frame) => frame[key]);
    expect(Math.max(...values) - Math.min(...values)).toBeLessThanOrEqual(0.5);
  }
  await expect(revenueChart).toHaveAttribute("data-chart-motion", "idle", { timeout: 2_000 });

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expect(page.locator(".admin-revenue-chart-body")).toHaveAttribute(
    "data-chart-motion",
    "idle"
  );
  await page.getByRole("tab", { name: "90 дн.", exact: true }).click();
  await expect(page.locator(".admin-revenue-chart-body")).toHaveAttribute(
    "data-chart-motion",
    "idle"
  );
});

test("partner dashboard tables stay compact, sortable, and show six rows", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(
    "/demo/runtime/admin/partners?partner_admin_scenario=populated&theme_preview=dark"
  );

  const dashboardTables = page.locator(".partners-dashboard-table-card");
  await expect(dashboardTables).toHaveCount(2);
  await expect(dashboardTables.nth(0).locator("tbody tr")).toHaveCount(6);
  await expect(dashboardTables.nth(1).locator("tbody tr")).toHaveCount(6);

  const earnedHeader = dashboardTables
    .nth(1)
    .getByRole("columnheader", { name: /Чистая комиссия/ });
  await expect(earnedHeader).toHaveAttribute("aria-sort", "descending");
  await earnedHeader.getByRole("button").click();
  await expect(earnedHeader).toHaveAttribute("aria-sort", "ascending");

  const rowHeights = await dashboardTables
    .first()
    .locator("tbody tr")
    .evaluateAll((rows) => rows.map((row) => row.getBoundingClientRect().height));
  expect(Math.max(...rowHeights)).toBeLessThanOrEqual(44);

  const dashboardGeometry = await dashboardTables.evaluateAll((cards) =>
    cards.map((card) => ({
      card: card.getBoundingClientRect().height,
      header: card.querySelector("header")?.getBoundingClientRect().height ?? 0,
    }))
  );
  expect(Math.abs(dashboardGeometry[0].header - dashboardGeometry[1].header)).toBeLessThanOrEqual(
    1
  );
  expect(Math.abs(dashboardGeometry[0].card - dashboardGeometry[1].card)).toBeLessThanOrEqual(1);

  await dashboardTables
    .first()
    .locator("tbody tr")
    .evaluateAll((rows) => rows.slice(2).forEach((row) => row.remove()));
  const unequalListHeights = await dashboardTables.evaluateAll((cards) =>
    cards.map((card) => card.getBoundingClientRect().height)
  );
  expect(Math.abs(unequalListHeights[0] - unequalListHeights[1])).toBeLessThanOrEqual(1);
});

test("crypto withdrawals require settlement data before they can be marked paid", async ({
  page,
}) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(
    "/demo/runtime/admin/partners/withdrawals/WD-499?partner_admin_scenario=populated&theme_preview=dark"
  );

  const settlement = page.getByLabel("Фактическая сумма в криптовалюте");
  await expect(settlement).toBeVisible();
  await page.getByRole("button", { name: "Отметить выплаченным" }).click();
  await expect(settlement).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("alert")).toContainText("Укажите фактическую сумму");

  await settlement.fill("125.50 USDT");
  await page.getByRole("button", { name: "Отметить выплаченным" }).click();
  await expect(page.locator(".partners-record-card > header")).toContainText("Выплачен");
  await expect(page.getByRole("status")).toContainText("Вывод отмечен выплаченным");

  await page.getByRole("tab", { name: "Партнёры", exact: true }).click();
  await expect(page.locator(".partners-success-banner")).toHaveCount(0);
});

test("broadcast promo picker fills its mobile editor row", async ({ page }) => {
  await page.setViewportSize(MOBILE_VIEWPORT);
  await page.goto("/demo/runtime/admin/broadcast?theme_preview=dark");

  await page.getByRole("button", { name: "Добавить кнопку", exact: true }).click();
  const row = page.locator(".admin-row-editor-broadcast").first();
  await row.getByRole("button", { name: "Кнопки", exact: true }).click();
  await page.getByRole("option", { name: "Промокод — в боте", exact: true }).click();

  const kindSelect = row.locator(".admin-select-trigger");
  const combo = row.locator(".admin-combobox");
  const input = row.getByRole("combobox", { name: "Выберите промокод", exact: true });
  const trigger = row.getByRole("button", { name: "Выберите промокод", exact: true });
  await input.click();
  const menu = page.locator(".admin-combobox-content");
  await expect(menu).toBeVisible();

  const rect = async (locator: Locator) =>
    locator.evaluate((element) => {
      const bounds = element.getBoundingClientRect();
      return {
        bottom: bounds.bottom,
        left: bounds.left,
        right: bounds.right,
        top: bounds.top,
        width: bounds.width,
      };
    });
  await expect
    .poll(async () => Math.abs((await rect(menu)).width - (await rect(combo)).width))
    .toBeLessThanOrEqual(1);
  const [kindRect, comboRect, inputRect, triggerRect, menuRect] = await Promise.all([
    rect(kindSelect),
    rect(combo),
    rect(input),
    rect(trigger),
    rect(menu),
  ]);

  expect(Math.abs(comboRect.width - kindRect.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(inputRect.width - comboRect.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(menuRect.width - comboRect.width)).toBeLessThanOrEqual(1);
  expect(triggerRect.left).toBeGreaterThanOrEqual(inputRect.left);
  expect(triggerRect.right).toBeLessThanOrEqual(inputRect.right);
  expect(triggerRect.top).toBeGreaterThanOrEqual(inputRect.top);
  expect(triggerRect.bottom).toBeLessThanOrEqual(inputRect.bottom);
});

test("message button editor offers the partner program screen", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto("/demo/runtime/admin/broadcast?theme_preview=dark");

  await page.getByRole("button", { name: "Добавить кнопку", exact: true }).click();
  const row = page.locator(".admin-row-editor-broadcast").first();
  await row.getByRole("button", { name: "Кнопки", exact: true }).click();
  await page.getByRole("option", { name: "Экран веб-приложения", exact: true }).click();

  const sectionSelect = row.getByRole("button", { name: "Выберите экран", exact: true });
  await sectionSelect.click();
  await page.getByRole("option", { name: "Партнёрская программа", exact: true }).click();

  await expect(sectionSelect).toContainText("Партнёрская программа");
});

test("checkout sliders track dragging without transition lag, animate prices, and defer quotes", async ({
  page,
}) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  let quoteRequests = 0;
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (
      path.endsWith("/api/subscription/quote") ||
      path.endsWith("/api/subscription/quote-promo")
    ) {
      quoteRequests += 1;
    }
  });

  await page.goto("/demo/runtime/home?mock=checkout-addons");
  await expect(page.locator("nav.bottom-nav")).toBeVisible();
  const paymentOpened = await clickFirstVisibleEnabled(webappAction(page, "open-payment"));
  expect(paymentOpened).toBe(true);

  const dialog = page.locator(".dialog-card.webapp-payment-dialog");
  await expect(dialog).toBeVisible();
  const tariffRows = dialog.locator(".tariff-row");
  if ((await tariffRows.count()) > 0) {
    await tariffRows.first().click();
    const nextButton = dialog.locator(".payment-submit-button").first();
    if (!(await nextButton.isDisabled())) await nextButton.click();
  }

  await expect(dialog.locator(".dialog-head h2")).toHaveCount(0);
  await expect(dialog.locator(".dialog-head .subscription-purchase-description")).toBeVisible();
  await expect(
    dialog.locator(".payment-dialog-body > .subscription-purchase-description")
  ).toHaveCount(0);

  const promoInput = dialog.locator(".checkout-promo-input");
  const promoApplyButton = dialog.locator(".checkout-promo-action .btn");
  await expect(promoInput).toBeEditable();
  await promoInput.pressSequentially("SAVE20");
  await expect(promoInput).toHaveValue("SAVE20");
  await expect(promoApplyButton).toBeEnabled();
  await promoApplyButton.click();
  await expect(promoInput).toHaveAttribute("readonly", "");
  await expect(dialog.locator(".checkout-promo-discount-marker")).toBeVisible();

  const dialogInsets = await dialog.evaluate((element) => {
    const dialogRect = element.getBoundingClientRect();
    const headerRect = element.querySelector(".dialog-head")!.getBoundingClientRect();
    const closeRect = element.querySelector(".dialog-close-button")!.getBoundingClientRect();
    return {
      headerLeft: headerRect.left - dialogRect.left,
      headerRight: dialogRect.right - headerRect.right,
      closeTop: closeRect.top - dialogRect.top,
      closeRight: dialogRect.right - closeRect.right,
    };
  });
  expect(Math.abs(dialogInsets.headerLeft - dialogInsets.headerRight)).toBeLessThanOrEqual(1);
  expect(Math.abs(dialogInsets.closeTop - dialogInsets.closeRight)).toBeLessThanOrEqual(1);

  const summary = dialog.locator(".checkout-tariff-summary-button");
  await expect(summary).toBeVisible();
  await summary.click();

  const slider = dialog.locator(".checkout-slider").first();
  const priceFlows = dialog.locator("number-flow-svelte");
  await expect(slider).toBeVisible();
  await expect(priceFlows.first()).toBeVisible();
  await page.waitForTimeout(1_050);

  const sliderBox = await slider.boundingBox();
  expect(sliderBox, "checkout slider must have a draggable box").not.toBeNull();
  if (!sliderBox) return;

  const quoteRequestsBeforeDrag = quoteRequests;
  const sliderY = sliderBox.y + sliderBox.height / 2;
  await page.mouse.move(sliderBox.x + sliderBox.width * 0.15, sliderY);
  await page.mouse.down();
  await expect(slider).toHaveClass(/is-interacting/);
  await expect(slider.locator(".checkout-slider-range")).toHaveCSS("transition-duration", "0s");
  const readAnimationState = () =>
    priceFlows.evaluateAll((nodes) =>
      nodes.map((node) => {
        const flow = node as HTMLElement & { animated?: boolean };
        return {
          animated: flow.animated,
          running:
            flow.shadowRoot
              ?.getAnimations()
              .filter((animation) => animation.playState === "running").length ?? 0,
        };
      })
    );

  await page.mouse.move(sliderBox.x + sliderBox.width * 0.85, sliderY, { steps: 3 });
  await page.waitForTimeout(60);
  const initialAnimationState = await readAnimationState();
  for (let cycle = 0; cycle < 4; cycle += 1) {
    await page.mouse.move(sliderBox.x + sliderBox.width * 0.15, sliderY, { steps: 3 });
    await page.waitForTimeout(110);
    await page.mouse.move(sliderBox.x + sliderBox.width * 0.85, sliderY, { steps: 3 });
    await page.waitForTimeout(110);
  }

  const finalAnimationState = await readAnimationState();
  const runningAnimations = (states: { running: number }[]) =>
    states.reduce((total, { running }) => total + running, 0);
  expect(finalAnimationState.length).toBeGreaterThan(0);
  expect(
    finalAnimationState.every(({ animated }) => animated !== false),
    JSON.stringify(finalAnimationState)
  ).toBe(true);
  expect(runningAnimations(initialAnimationState)).toBeGreaterThan(0);
  expect(runningAnimations(finalAnimationState)).toBeGreaterThan(0);
  expect(runningAnimations(finalAnimationState)).toBeLessThanOrEqual(
    runningAnimations(initialAnimationState) * 2
  );
  expect(quoteRequests).toBe(quoteRequestsBeforeDrag);

  await page.mouse.up();
  await expect(slider).not.toHaveClass(/is-interacting/);
  await page.waitForTimeout(250);
  expect(quoteRequests).toBeLessThanOrEqual(quoteRequestsBeforeDrag + 1);
  await expect(promoInput).toHaveValue("SAVE20");
  await expect(promoInput).toHaveAttribute("readonly", "");
  await expect(dialog.locator(".checkout-promo-discount-marker")).toBeVisible();
  await closeDialog(dialog);
});

test("public install share links survive browser focus and visibility changes", async ({
  page,
}) => {
  const sharePath = "/s/0123456789abcdef0123456789abcdef";
  await page.clock.install();
  await page.goto(sharePath);
  const publicShell = page.locator(".public-install-shell");
  await expect(publicShell).toBeVisible();
  const shareUrl = page.url();

  for (const event of ["blur", "hidden", "visible", "focus", "pageshow"]) {
    await page.evaluate((event) => {
      if (event === "hidden" || event === "visible") {
        Object.defineProperty(document, "visibilityState", { configurable: true, value: event });
        document.dispatchEvent(new Event("visibilitychange"));
      } else {
        window.dispatchEvent(new Event(event));
      }
    }, event);
    await page.clock.runFor(1_000);
    await expect(page).toHaveURL(shareUrl);
    await expect(publicShell).toBeVisible();
  }
});

test("checkout promo code is editable and applies its quoted discount", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto("/demo/runtime/home?mock=checkout-no-addons");
  await expect(page.locator("nav.bottom-nav")).toBeVisible();
  expect(await clickFirstVisibleEnabled(webappAction(page, "open-payment"))).toBe(true);

  const dialog = page.locator(".dialog-card.webapp-payment-dialog");
  await expect(dialog).toBeVisible();
  const tariffRows = dialog.locator(".tariff-row");
  if ((await tariffRows.count()) > 0) {
    await tariffRows.first().click();
    const nextButton = dialog.locator(".payment-submit-button").first();
    if (!(await nextButton.isDisabled())) await nextButton.click();
  }

  const promoInput = dialog.locator(".checkout-promo-input");
  const promoApplyButton = dialog.locator(".checkout-promo-action .btn");
  await expect(promoInput).toBeEditable();
  await promoInput.fill("save20");
  await expect(promoApplyButton).toBeEnabled();
  await promoApplyButton.click();

  await expect(promoInput).toHaveValue("SAVE20");
  await expect(promoInput).toHaveAttribute("readonly", "");
  await expect(dialog.locator(".checkout-promo-discount-marker")).toBeVisible();
});

test("admin deep links do not pin the first opened record", async ({ page }) => {
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await page.goto(`${APP_URL}?screen=admin&admin_section=payments`);

  const paymentUserButtons = page.locator(".admin-payments-table .admin-payments-user-btn");
  await expect(paymentUserButtons.nth(1)).toBeVisible();
  await paymentUserButtons.first().click();

  const firstPaymentUserId = new URL(page.url()).pathname.split("/").pop();
  expect(firstPaymentUserId).toBeTruthy();
  await page.reload();

  const userDialog = page.locator(".dialog-card.admin-user-dialog");
  await expect(userDialog).toBeVisible();
  await expect(userDialog.locator(".dialog-title-copy h2")).toContainText(`#${firstPaymentUserId}`);
  await closeDialog(userDialog);

  await paymentUserButtons.nth(1).click();
  const secondPaymentUserId = new URL(page.url()).pathname.split("/").pop();
  expect(secondPaymentUserId).toBeTruthy();
  expect(secondPaymentUserId).not.toBe(firstPaymentUserId);
  await expect(userDialog.locator(".dialog-title-copy h2")).toContainText(
    `#${secondPaymentUserId}`
  );
  await closeDialog(userDialog);

  const paymentButtons = page.locator(".admin-payments-table .admin-payment-id-btn");
  await expect(paymentButtons.nth(1)).toBeVisible();
  await paymentButtons.first().click();
  const firstPaymentId = new URL(page.url()).pathname.split("/").pop();
  expect(firstPaymentId).toBeTruthy();
  await page.reload();

  const paymentDialog = page.locator(".dialog-card.admin-payment-dialog");
  await expect(paymentDialog).toBeVisible();
  await expect(paymentDialog.locator(".dialog-title-copy h2")).toContainText(`#${firstPaymentId}`);
  await closeDialog(paymentDialog);

  await paymentButtons.nth(1).click();
  const secondPaymentId = new URL(page.url()).pathname.split("/").pop();
  expect(secondPaymentId).toBeTruthy();
  expect(secondPaymentId).not.toBe(firstPaymentId);
  await expect(paymentDialog.locator(".dialog-title-copy h2")).toContainText(`#${secondPaymentId}`);
  await closeDialog(paymentDialog);

  await openAdminSection(page, "users");
  const userRows = activeAdminSection(page, "users").locator("tr[data-user-id]");
  await expect(userRows.nth(1)).toBeVisible();
  await userRows.first().click();
  const firstUserId = new URL(page.url()).pathname.split("/").pop();
  expect(firstUserId).toBeTruthy();
  await page.reload();

  await expect(userDialog).toBeVisible();
  await expect(userDialog.locator(".dialog-title-copy h2")).toContainText(`#${firstUserId}`);
  await closeDialog(userDialog);

  await userRows.nth(1).click();
  const secondUserId = new URL(page.url()).pathname.split("/").pop();
  expect(secondUserId).toBeTruthy();
  expect(secondUserId).not.toBe(firstUserId);
  await expect(userDialog.locator(".dialog-title-copy h2")).toContainText(`#${secondUserId}`);
});

test("webapp and admin sections, dialogs, tabs stay interactive without console errors", async ({
  page,
}) => {
  let phase = "boot";
  const setPhase = (value: string) => {
    phase = value;
  };
  const errors = trackErrors(page, () => phase);

  // Exercise the separately mounted admin bundle with a warning-bearing archive.
  // A warning-free listing never creates Tooltip.Root and hides missing context.
  await page.addInitScript(() => {
    type AdminProps = Record<string, unknown> & {
      api: (path: string, options?: RequestInit) => Promise<Record<string, unknown>>;
    };
    type AdminBundle = {
      mount: (target: HTMLElement, props: AdminProps) => unknown;
    };
    let bundle: AdminBundle | undefined;
    Object.defineProperty(window, "SubscriptionWebAppAdmin", {
      configurable: true,
      get: () => bundle,
      set(value: AdminBundle) {
        const mount = value.mount;
        value.mount = (target, props) =>
          mount(target, {
            ...props,
            api: async (path, options) => {
              const response = await props.api(path, options);
              if (path === "/admin/backups" && Array.isArray(response.archives)) {
                return {
                  ...response,
                  archives: response.archives.map((archive, index) => ({
                    ...archive,
                    warnings: index === 0 ? ["Archive warning fixture"] : [],
                  })),
                };
              }
              return response;
            },
          });
        bundle = value;
      },
    });
  });

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

  setPhase("admin-dashboard:panel-version");
  const panelVersionTrigger = activeAdminSection(page, "stats").locator(
    ".admin-panel-version-trigger"
  );
  await expect(panelVersionTrigger).toBeVisible();
  await expect(panelVersionTrigger).toContainText("v3.4.4");
  await panelVersionTrigger.click();
  const panelVersionPopover = page.locator(".admin-panel-version-popover");
  await expect(panelVersionPopover).toBeVisible();
  await expect(panelVersionPopover).toContainText("Точная версия проверена");
  await expect(panelVersionPopover).toContainText("Проверенные версии");
  await page.keyboard.press("Escape");
  await expect(panelVersionPopover).toBeHidden();

  setPhase("admin-dashboard:user-filter-link");
  const paidUsersCounter = activeAdminSection(page, "stats").locator(
    '[data-admin-user-filter="paid"]'
  );
  await expect(paidUsersCounter).toBeVisible();
  await paidUsersCounter.click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/users\?users_filter=paid$/);
  await expect(activeAdminSection(page, "users")).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/stats$/);
  await expect(activeAdminSection(page, "stats")).toBeVisible();

  setPhase("admin-dashboard:revenue-chart-hover");
  const revenueChart = activeAdminSection(page, "stats").locator(".admin-revenue-chart-body");
  const revenueChartOver = revenueChart.locator(".u-over");
  await revenueChart.scrollIntoViewIfNeeded();
  await expect(revenueChartOver).toBeVisible();
  const revenueChartOverBox = await revenueChartOver.boundingBox();
  if (!revenueChartOverBox) throw new Error("revenue chart hover surface has no bounding box");
  await revenueChartOver.hover({
    position: { x: revenueChartOverBox.width / 2, y: revenueChartOverBox.height / 2 },
  });
  await expect(revenueChart.locator(".admin-chart-tooltip.is-visible")).toBeVisible();
  await expect(revenueChart.locator(".admin-chart-highlight.is-visible")).toBeVisible();
  const firstTooltipBox = await revenueChart
    .locator(".admin-chart-tooltip.is-visible")
    .boundingBox();
  const firstHighlightCentre = await chartHighlightCentre(revenueChart);
  await revenueChartOver.hover({
    position: { x: revenueChartOverBox.width - 2, y: revenueChartOverBox.height / 2 },
  });
  await page.waitForTimeout(400);
  const secondHighlightCentre = await chartHighlightCentre(revenueChart);
  expect(secondHighlightCentre).not.toBeNull();
  expect(Math.abs((secondHighlightCentre ?? 0) - (firstHighlightCentre ?? 0))).toBeGreaterThan(20);
  const revenueWrapBox = await revenueChart.locator(".admin-revenue-uplot-wrap").boundingBox();
  const revenueTooltipBox = await revenueChart
    .locator(".admin-chart-tooltip.is-visible")
    .boundingBox();
  if (!revenueWrapBox || !revenueTooltipBox) {
    throw new Error("revenue chart tooltip has no bounding box");
  }
  if (!firstTooltipBox) throw new Error("revenue chart tooltip has no initial bounding box");
  const revenueTooltipLaneBox = await revenueChart
    .locator(".admin-chart-tooltip-lane")
    .boundingBox();
  const revenueHighlightBox = await revenueChart
    .locator(".admin-chart-highlight.is-visible")
    .boundingBox();
  // The readout's notch comes from the shared `Plate` component.
  const revenueTooltipArrowBox = await revenueChart
    .locator(".admin-chart-tooltip .ui-plate-arrow")
    .boundingBox();
  if (
    !revenueTooltipLaneBox ||
    !revenueHighlightBox ||
    !revenueTooltipArrowBox ||
    secondHighlightCentre === null
  ) {
    throw new Error("revenue chart overlay geometry is unavailable");
  }
  const highlightDotX = revenueHighlightBox.x + secondHighlightCentre;
  const tooltipArrowX = revenueTooltipArrowBox.x + revenueTooltipArrowBox.width / 2;
  expect(Math.abs(revenueTooltipBox.y - firstTooltipBox.y)).toBeLessThanOrEqual(1);
  expect(revenueTooltipLaneBox.y).toBeGreaterThanOrEqual(revenueWrapBox.y + revenueWrapBox.height);
  expect(Math.abs(revenueHighlightBox.width - revenueWrapBox.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(revenueHighlightBox.height - revenueWrapBox.height)).toBeLessThanOrEqual(1);
  // The card is clamped at the extreme right; its arrow keeps a safe inset
  // from the rounded corner while staying visually attached to the point.
  expect(Math.abs(tooltipArrowX - highlightDotX)).toBeLessThanOrEqual(12);
  expect(
    revenueWrapBox.x + revenueWrapBox.width - revenueTooltipBox.x - revenueTooltipBox.width
  ).toBeGreaterThanOrEqual(7);

  setPhase("admin-section-registry");
  for (const id of CORE_ADMIN_SECTION_IDS) {
    await expect(adminSectionButton(page, id), `core admin section exists: ${id}`).toBeVisible();
  }

  for (const id of CORE_ADMIN_SECTION_IDS) {
    setPhase(`admin-section:${id}`);
    await openAdminSection(page, id);
  }

  setPhase("admin-backups:archive-contents");
  const backupsStage = await openAdminSection(page, "backups");
  await expect(backupsStage.getByRole("checkbox", { name: "БД" })).toBeEnabled();
  await expect(backupsStage.getByRole("checkbox", { name: "compose-папка" })).toBeEnabled();
  await expect(backupsStage.locator(".backups-badges").first()).toContainText("БД");
  await expect(backupsStage.locator(".backups-badges").first()).toContainText("Compose");
  const backupWarning = backupsStage.getByRole("button", { name: "Archive warning fixture" });
  await backupWarning.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(backupWarning).toBeFocused();
  const backupTooltip = page.locator(".backups-warning-tooltip");
  await expect(backupTooltip).toBeVisible();
  await expect(backupTooltip).toContainText("Archive warning fixture");
  await page.keyboard.press("Escape");
  await expect(backupTooltip).toHaveCount(0);
  await backupsStage.getByRole("button", { name: "Обновить", exact: true }).click();
  await expect(backupWarning).toBeVisible();
  await expect(backupsStage.getByRole("radio")).toHaveCount(2);

  setPhase("admin-broadcast:shortcode-picker");
  await openAdminSection(page, "broadcast");
  const shortcodeToggle = page.locator("[data-rt-shortcodes-toggle]");
  await expect(shortcodeToggle).toBeVisible();
  await shortcodeToggle.click();
  const shortcodeList = page.locator(".rt-menu-list");
  await expect(shortcodeList).toBeVisible();
  await expect(shortcodeList.locator(".rt-menu-scroll .scroll-area__viewport")).toBeVisible();
  await shortcodeList.locator(".rt-menu-item").first().click();
  await expect(page.locator(".rt-surface .rt-chip").first()).toBeVisible();
  await page.locator("[data-rt-source-toggle]").click();
  const broadcastSource = page.locator("textarea.rt-source");
  await expect(broadcastSource).toBeVisible();
  await broadcastSource.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement;
    textarea.focus();
    textarea.setSelectionRange(0, textarea.value.length);
  });
  await page.locator('[data-rt-format="bold"]').click();
  await expect(broadcastSource).toHaveValue("<b>{first_name}</b>");
  await broadcastSource.evaluate((element) => {
    const textarea = element as HTMLTextAreaElement;
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
  });
  await page.locator('[data-rt-format="link"]').click();
  await expect(broadcastSource).toHaveValue('<b>{first_name}</b><a href="https://">https://</a>');
  await page.locator("[data-rt-source-toggle]").click();
  await expect(page.locator(".rt-surface .rt-chip").first()).toBeVisible();

  setPhase("admin-users:filter-dialog");
  await openAdminSection(page, "users");
  await page.setViewportSize(MOBILE_VIEWPORT);
  await expect(page.locator(".admin-users-filter-toggle")).toBeVisible();
  await page.locator(".admin-users-filter-toggle").click();
  const usersFilterDialog = page.locator(".dialog-card.admin-users-filter-dialog");
  await expect(usersFilterDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-users:filter-dialog");
  await closeDialog(usersFilterDialog);
  const usersShell = page.locator(".admin-users-table-wrap");
  const mobileUserCard = usersShell.locator(".admin-user-mobile-card").first();
  await expect(mobileUserCard).toBeVisible();
  await expect(usersShell.locator(".admin-table-wrap")).toBeHidden();
  await expect(mobileUserCard.locator(".admin-user-mobile-metrics > div")).toHaveCount(4);
  await expect(mobileUserCard.locator(".admin-user-mobile-dates > div")).toHaveCount(2);
  const mobileUsersGeometry = await usersShell.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
  }));
  expect(mobileUsersGeometry.scrollWidth).toBeLessThanOrEqual(mobileUsersGeometry.clientWidth);
  const mobileUserCardBox = await mobileUserCard.boundingBox();
  expect(mobileUserCardBox).not.toBeNull();
  expect(mobileUserCardBox!.height).toBeLessThan(320);
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await expect(adminSidebar).toBeVisible();

  setPhase("admin-users:row-card");
  await page.locator("tr[data-user-id]").first().click();
  await openUserDetailFromCurrentSection(page, setPhase, "admin-users", {
    checkBalanceTileSelection: true,
    checkMobileTariffTapThrough: true,
  });
  await page.setViewportSize(DESKTOP_VIEWPORT);

  setPhase("admin-payments:mobile-list");
  await openAdminSection(page, "payments");
  await page.setViewportSize(MOBILE_VIEWPORT);
  const paymentsShell = page.locator(".admin-payments-table-shell");
  const mobilePaymentCard = paymentsShell.locator(".admin-payment-mobile-card").first();
  await expect(mobilePaymentCard).toBeVisible();
  await expect(paymentsShell.locator(".admin-table-wrap")).toBeHidden();
  await expect(paymentsShell.locator(".admin-payments-table")).toBeHidden();
  const mobilePaymentsGeometry = await paymentsShell.evaluate((element) => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth,
    documentClientWidth: document.documentElement.clientWidth,
    documentScrollWidth: document.documentElement.scrollWidth,
  }));
  expect(mobilePaymentsGeometry.scrollWidth).toBeLessThanOrEqual(
    mobilePaymentsGeometry.clientWidth
  );
  expect(mobilePaymentsGeometry.documentScrollWidth).toBeLessThanOrEqual(
    mobilePaymentsGeometry.documentClientWidth
  );
  const mobilePaymentCardBox = await mobilePaymentCard.boundingBox();
  expect(mobilePaymentCardBox).not.toBeNull();
  expect(mobilePaymentCardBox!.height).toBeLessThan(300);
  await expect(mobilePaymentCard.locator(".admin-payment-mobile-metrics dd")).toHaveCount(2);
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value: string) => {
          document.documentElement.dataset.copiedValue = value;
        },
      },
    });
  });
  const mobilePaymentId = await mobilePaymentCard.getAttribute("data-mobile-payment-id");
  await mobilePaymentCard.locator('[data-copy-kind="payment-id"]').click();
  await expect(page.locator("html")).toHaveAttribute("data-copied-value", mobilePaymentId!);
  await expect(page.getByText("Значение скопировано", { exact: true }).last()).toBeVisible();
  await page.setViewportSize(DESKTOP_VIEWPORT);
  await expect(adminSidebar).toBeVisible();

  setPhase("admin-payments:payment-dialog");
  await page.locator(".admin-payment-id-btn").first().click();
  const paymentDialog = page.locator(".dialog-card.admin-payment-dialog");
  await expect(paymentDialog).toBeVisible();
  await assertFormFieldsNamed(page, "admin-payments:payment-dialog");
  await paymentDialog
    .getByRole("button", { name: "Открыть карточку пользователя", exact: true })
    .click();
  await expect(paymentDialog).toBeHidden();
  await openUserDetailFromCurrentSection(page, setPhase, "admin-payment-detail");

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
  await expect(createCodeDialog.locator(".admin-promo-effect-row")).toHaveCount(6);
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
  await tariffDialog.getByRole("tab").nth(1).click();
  const periodRows = tariffDialog.locator(".admin-row-editor-period:not(.admin-row-editor-header)");
  await expect(periodRows).toHaveCount(4);
  for (const [index, days] of ["30", "90", "180", "365"].entries()) {
    await expect(
      periodRows.nth(index).getByRole("spinbutton", { name: "Срок, дней", exact: true })
    ).toHaveValue(days);
  }
  await exerciseDialogTabs(tariffDialog, 5, setPhase, "admin-tariffs:edit-tabs");

  setPhase("admin-tariffs:edit-save");
  await tariffDialog.getByRole("tab").nth(2).click();
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
  await expect(appearanceStage.locator(".appearance-library")).toBeVisible();
  await expect(appearanceStage.locator(".library-theme-card")).toHaveCount(3);
  await assertFormFieldsNamed(page, "admin-appearance:panels");

  setPhase("admin-appearance:theme-card-select");
  const inactiveThemeCard = appearanceStage.locator(".library-theme-card:not(.active)").first();
  const inactiveThemeKey = await inactiveThemeCard.getAttribute("data-theme-key");
  await inactiveThemeCard.getByRole("button", { name: "Активировать", exact: true }).click();
  await expect(
    appearanceStage.locator('.library-theme-card[data-theme-key="' + inactiveThemeKey + '"]')
  ).toHaveClass(/active/);
  const defaultCard = appearanceStage.locator('.library-theme-card[data-theme-key="dark"]');
  await defaultCard.getByRole("button", { name: "Активировать", exact: true }).click();
  await expect(defaultCard).toHaveClass(/active/);
  await defaultCard.locator(".theme-card-actions button").last().click();
  const appearanceSettingsDialog = page.locator(".appearance-settings-dialog");
  await expect(appearanceSettingsDialog.locator(".default-theme-editor")).toBeVisible();
  await assertFormFieldsNamed(page, "admin-appearance:default-editor");
  await appearanceSettingsDialog.locator(".dialog-head button").click();
  await expect(appearanceSettingsDialog).toBeHidden();
  await appearanceStage.locator(".appearance-preferences-trigger").click();
  await expect(appearanceStage.locator(".appearance-logo-grid").first()).toBeVisible();
  await assertFormFieldsNamed(page, "admin-appearance:brand-editor");

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
