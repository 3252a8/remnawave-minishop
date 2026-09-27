import { expect, test, type ConsoleMessage, type Locator, type Page } from "@playwright/test";

const ADMIN_URL = "/demo/runtime/admin/stats?theme_preview=dark&mock=checkout-addons";

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message: ConsoleMessage) => {
    if (message.type() === "error" && !/favicon|telegram\.org/i.test(message.text())) {
      errors.push(`console.error: ${message.text()}`);
    }
  });
  page.on("pageerror", (error: Error) => errors.push(`pageerror: ${error.message}`));
  return errors;
}

async function openDocuments(page: Page, device: "desktop" | "mobile"): Promise<Locator> {
  if (device === "mobile") await page.locator(".admin-mobile-toggle").click();
  await page.locator('[data-admin-section="documents"]').click();
  await expect(page).toHaveURL(/\/demo\/runtime\/admin\/documents/);
  const documents = page.locator(
    '.admin-section-stage[data-admin-active-section="documents"]:not([inert])'
  );
  await expect(documents).toBeVisible();
  return documents;
}

for (const [scenario, device, viewport, telegram] of [
  ["desktop browser", "desktop", { width: 1440, height: 900 }, false],
  ["mobile browser", "mobile", { width: 390, height: 844 }, false],
  ["Telegram portrait", "mobile", { width: 390, height: 844 }, true],
  ["Telegram landscape", "mobile", { width: 740, height: 390 }, true],
] as const) {
  test(`documents have their own System editor on ${scenario}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    if (telegram) {
      await page.addInitScript(() => {
        Object.assign(window, {
          Telegram: {
            WebApp: {
              expand() {},
              initData: "",
              isFullscreen: true,
              isVersionAtLeast: () => true,
              offEvent() {},
              onEvent() {},
              platform: "ios",
              ready() {},
            },
          },
        });
        document.addEventListener("DOMContentLoaded", () => {
          const style = document.documentElement.style;
          style.setProperty("--tg-content-safe-area-inset-top", "110px");
          style.setProperty("--tg-content-safe-area-inset-bottom", "34px");
          style.setProperty("--tg-content-safe-area-inset-left", "20px");
          style.setProperty("--tg-content-safe-area-inset-right", "20px");
        });
      });
    }
    const errors = trackErrors(page);
    await page.route("https://example.test/logo.png", (route) =>
      route.fulfill({
        contentType: "image/svg+xml",
        body: '<svg xmlns="http://www.w3.org/2000/svg" />',
      })
    );
    await page.goto(ADMIN_URL);
    const documents = await openDocuments(page, device);

    await expect(page.locator(".admin-header h2", { hasText: "Документы" })).toHaveCount(1);
    await expect(
      page.locator(".admin-header small", {
        hasText: "Публичные Markdown-страницы, видимость и юридические роли",
      })
    ).toHaveCount(1);
    await expect(documents.locator(".documents-toolbar")).toHaveCount(0);
    await expect(documents.getByText("Документов пока нет", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Новый документ", exact: true })).toHaveCount(1);
    await page.locator('[data-admin-action="create-document"]').click();

    const dialog = page.locator(".dialog-card.admin-document-editor");
    await expect(dialog).toBeVisible();
    await expect(dialog).toHaveCSS("transform", "none");
    const dialogBox = await dialog.boundingBox();
    expect(dialogBox?.width).toBeGreaterThan(device === "desktop" ? 700 : 340);
    expect(dialogBox?.height).toBeLessThanOrEqual(viewport.height - 12);
    if (telegram) {
      expect(dialogBox!.y).toBeGreaterThanOrEqual(110);
      expect(dialogBox!.y + dialogBox!.height).toBeLessThanOrEqual(viewport.height - 34);
      expect(dialogBox!.x).toBeGreaterThanOrEqual(20);
      expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(viewport.width - 20);
      await dialog.locator(".dialog-close-button").click({ trial: true });
      await page.screenshot({ path: testInfo.outputPath("document-safe-area.png") });
    }

    const visualEditor = dialog.locator(".ProseMirror");
    const editorSurface = dialog.locator(".rt-surface");
    await expect(visualEditor).toBeVisible();
    await expect(visualEditor).toBeFocused();
    const emptyParagraph = visualEditor.locator("p.is-editor-empty");
    await expect
      .poll(() =>
        emptyParagraph.evaluate((element) => getComputedStyle(element, "::before").content)
      )
      .toContain("Текст документа...");

    await dialog.getByLabel("Название", { exact: true }).fill(`Документ ${device}`);
    const slug = dialog.getByPlaceholder("privacy-policy", { exact: true });
    const publicSlug = `support/guides/document-${device}`;
    await slug.click();
    await slug.press("ControlOrMeta+A");
    await slug.pressSequentially(`/${publicSlug}`);
    await dialog
      .getByPlaceholder("Юридическая информация", { exact: true })
      .fill("Юридические документы");
    await dialog.getByLabel("Показывать в настройках пользователя", { exact: true }).click();
    await dialog.getByLabel("Показывать в сайдбаре", { exact: true }).click();

    await dialog.getByRole("button", { name: "Markdown", exact: true }).click();
    const markdown = dialog.locator("textarea.rt-source");
    await expect(markdown).toBeVisible();
    const longDocument = `# Документ ${device}\n\n${Array.from(
      { length: 120 },
      (_, index) => `- Paragraph ${index + 1}`
    ).join("\n")}`;
    await markdown.fill(longDocument);
    await expect
      .poll(() => markdown.evaluate((element) => element.scrollHeight > element.clientHeight))
      .toBe(true);
    await dialog.getByRole("button", { name: "Редактор", exact: true }).click();
    await expect(visualEditor).toBeFocused();
    const layout = await dialog.evaluate((element) => {
      const editor = element.querySelector<HTMLElement>(".ProseMirror");
      const footer = element.querySelector<HTMLElement>(".admin-dialog-actions");
      const editorBox = editor?.getBoundingClientRect();
      const footerBox = footer?.getBoundingClientRect();
      return {
        editorBeforeFooter: Boolean(editorBox && footerBox && editorBox.bottom <= footerBox.top),
      };
    });
    expect(layout).toEqual({ editorBeforeFooter: true });

    await dialog.getByRole("button", { name: "Markdown", exact: true }).click();
    const text = `# Документ ${device}\n\n- Первый пункт\n- Второй пункт\n\n![Logo](https://example.test/logo.png)\n\n| Item | Value |\n| --- | --- |\n| One | Two |`;
    await markdown.fill(text);
    await dialog.getByRole("button", { name: "Редактор", exact: true }).click();
    await editorSurface.click({ position: { x: 2, y: 2 } });
    await expect(visualEditor).toBeFocused();
    await visualEditor.press("End");
    await visualEditor.press("Enter");
    await visualEditor.pressSequentially("Extra text");
    await dialog.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(dialog).toBeHidden();

    const card = documents.locator(".document-card").filter({ hasText: `Документ ${device}` });
    await expect(card).toBeVisible();
    await expect(documents.getByRole("heading", { name: "Юридические документы" })).toBeVisible();
    await expect(card.getByText("В настройках", { exact: true })).toBeVisible();
    await expect(card.getByText("В сайдбаре", { exact: true })).toBeVisible();
    const publicLink = card.getByRole("link", { name: "Открыть", exact: true });
    await expect(publicLink).toHaveAttribute("href", `/demo/runtime/docs/${publicSlug}`);
    await expect(publicLink).toHaveAttribute("target", "_blank");

    await page.goto("/demo/runtime/settings?mock=checkout-addons");
    const settingsLink = page.getByRole("link", { name: `Документ ${device}`, exact: true });
    await expect(settingsLink).toHaveAttribute("href", `/demo/runtime/docs/${publicSlug}`);
    await settingsLink.click();
    await expect(page.locator(".information-markdown")).toContainText("Первый пункт");
    const publicPageGeometry = await page.locator(".information-page").evaluate((element) => {
      const topbar = element.querySelector<HTMLElement>(".information-page-topbar");
      const layout = element.querySelector<HTMLElement>(".information-page-layout");
      const topbarBox = topbar?.getBoundingClientRect();
      const layoutBox = layout?.getBoundingClientRect();
      return {
        topbarBottom: topbarBox?.bottom ?? 0,
        layoutTop: layoutBox?.top ?? 0,
      };
    });
    expect(publicPageGeometry.layoutTop - publicPageGeometry.topbarBottom).toBeLessThanOrEqual(32);

    await page.goto(ADMIN_URL);
    const reopenedDocuments = await openDocuments(page, device);
    const reopenedCard = reopenedDocuments
      .locator(".document-card")
      .filter({ hasText: `Документ ${device}` });
    await reopenedCard.getByRole("button", { name: "Редактировать документ", exact: true }).click();
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Markdown", exact: true }).click();
    await expect(markdown).toHaveValue(/!\[Logo\]\(https:\/\/example.test\/logo.png\)/);
    await expect(markdown).toHaveValue(/\| Item \| Value \|/);
    await expect(markdown).toHaveValue(/Extra text/);
    await dialog.locator(".dialog-head button").click();
    await expect(dialog).toBeHidden();

    expect(errors).toEqual([]);
  });
}
