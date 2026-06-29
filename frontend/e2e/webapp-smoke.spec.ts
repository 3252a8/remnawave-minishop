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

async function assertFormFieldsNamed(page: Page, phase: string): Promise<void> {
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

async function openUserDetailFromCurrentSection(
  page: Page,
  setPhase: (value: string) => void,
  phasePrefix: string
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
  await openUserDetailFromCurrentSection(page, setPhase, "admin-users");

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
  await closeDialog(tariffDialog);

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
