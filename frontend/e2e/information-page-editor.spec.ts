import { expect, test, type ConsoleMessage, type Locator, type Page } from "@playwright/test";

const ADMIN_URL = "/demo/runtime/admin/stats?theme_preview=dark&mock=checkout-addons";

for (const platform of ["ios", "android"] as const) {
  test(`document and Home restore Telegram viewport without launch parameters on ${platform}`, async ({
    page,
  }) => {
    const errors = trackErrors(page);
    let sdkLoads = 0;
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript(() => {
      window.sessionStorage.setItem(
        "minishop-demo-documents",
        JSON.stringify([
          {
            title: "Viewport document",
            slug: "viewport-document",
            show_in_settings: true,
            show_in_sidebar: true,
            markdown: "# Viewport document\n\nDocument content.",
          },
        ])
      );
    });
    await page.route("https://telegram.org/js/telegram-web-app.js*", (route) => {
      sdkLoads++;
      return route.fulfill({
        contentType: "application/javascript",
        body: `
        // Simulate the official SDK's saved initParams/fullscreen restoration.
        const saved = JSON.parse(sessionStorage.getItem('__telegram__initParams') || '{}');
        const params = { ...saved, ...Object.fromEntries(new URLSearchParams(location.hash.slice(1))) };
        sessionStorage.setItem('__telegram__initParams', JSON.stringify(params));
        if (params.tgWebAppFullscreen) sessionStorage.setItem('__telegram__isFullscreen', '"yes"');
        const handlers = new Map();
        const calls = { ready: 0, expand: 0 };
        const webApp = {
          initData: params.tgWebAppData || '', platform: params.tgWebAppPlatform || 'unknown',
          isFullscreen: JSON.parse(sessionStorage.getItem('__telegram__isFullscreen') || 'null') === 'yes',
          isVersionAtLeast: () => true,
          ready: () => calls.ready++, expand: () => calls.expand++,
          onEvent: (event, handler) => {
            const listeners = handlers.get(event) || new Set();
            listeners.add(handler); handlers.set(event, listeners);
          },
          offEvent: (event, handler) => handlers.get(event)?.delete(handler),
          requestFullscreen: () => {},
        };
        window.Telegram = { WebApp: webApp };
        window.telegramViewportTest = { calls, handlers, webApp };
      `,
      });
    });

    await page.goto(
      `/demo/runtime/app/?screen=settings&theme_preview=dark#tgWebAppVersion=8.0&tgWebAppPlatform=${platform}&tgWebAppData=test-signed-data&tgWebAppFullscreen=1`
    );
    const root = page.locator("html");
    await expect(root).toHaveAttribute("data-telegram-fullscreen", "true");
    const documentLink = page.getByRole("link", { name: "Viewport document", exact: true });
    await expect(documentLink).toBeVisible();
    await expect(documentLink).toHaveAttribute("href", "/demo/runtime/viewport-document");
    await documentLink.click();
    await expect(page.locator(".information-markdown")).toContainText("Document content.");
    await expect(root).toHaveAttribute("data-telegram-fullscreen", "true");
    expect(new URL(page.url()).search).toBe("");
    expect(new URL(page.url()).hash).toBe("");
    await expect
      .poll(() =>
        page
          .locator(".information-page-topbar")
          .evaluate((element) => element.getBoundingClientRect().top)
      )
      .toBe(96);
    const homeLink = page
      .locator(".information-page-topbar")
      .getByRole("link", { name: "Главная", exact: true });
    await expect(homeLink).toHaveAttribute("href", "/demo/runtime/");
    await homeLink.click();
    await expect(root).toHaveAttribute("data-telegram-fullscreen", "true");
    await expect(page.locator(".bottom-nav")).toBeVisible();
    expect(new URL(page.url()).search).toBe("");
    expect(new URL(page.url()).hash).toBe("");
    expect(sdkLoads).toBe(3);

    for (const label of ["Устройства", "Бонусы"]) {
      await page.locator(".bottom-nav").getByRole("button", { name: label, exact: true }).click();
      await expect
        .poll(() =>
          page
            .locator(".phone-screen")
            .evaluate((element) => Number.parseFloat(getComputedStyle(element).paddingTop))
        )
        .toBeGreaterThanOrEqual(96);
    }
    await page.setViewportSize({ width: 740, height: 390 });
    await page.evaluate(() => {
      // Official SDK safe-area events update CSS; consumers must use current values.
      const state = (
        window as unknown as {
          telegramViewportTest: {
            webApp: { isFullscreen: boolean };
            handlers: Map<string, Set<() => void>>;
          };
        }
      ).telegramViewportTest;
      document.documentElement.style.setProperty("--tg-content-safe-area-inset-top", "120px");
      state.handlers.get("activated")?.forEach((handler) => handler());
    });
    await expect
      .poll(() =>
        page
          .locator(".phone-screen")
          .evaluate((element) => Number.parseFloat(getComputedStyle(element).paddingTop))
      )
      .toBeGreaterThanOrEqual(120);
    const lifecycle = await page.evaluate(() => {
      const state = (
        window as unknown as {
          telegramViewportTest: {
            calls: { ready: number; expand: number };
            handlers: Map<string, Set<() => void>>;
          };
        }
      ).telegramViewportTest;
      return {
        calls: state.calls,
        viewportListeners: ["fullscreenChanged", "fullscreenFailed", "activated"].map(
          (event) => state.handlers.get(event)?.size
        ),
      };
    });
    expect(lifecycle).toEqual({ calls: { ready: 1, expand: 1 }, viewportListeners: [1, 1, 1] });
    expect(errors).toEqual([]);
  });
}

test("ordinary document navigation ignores corrupt Telegram and fullscreen-only storage", async ({
  page,
}) => {
  let sdkLoads = 0;
  await page.route("https://telegram.org/js/telegram-web-app.js*", (route) => {
    sdkLoads++;
    return route.fulfill({ contentType: "application/javascript", body: "" });
  });
  await page.addInitScript(() => {
    sessionStorage.setItem("__telegram__initParams", "broken JSON");
    sessionStorage.setItem("__telegram__isFullscreen", '"yes"');
    sessionStorage.setItem(
      "minishop-demo-documents",
      JSON.stringify([
        {
          title: "Browser document",
          slug: "browser-document",
          markdown: "Browser content.",
        },
      ])
    );
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/demo/runtime/browser-document?theme_preview=dark");
  await expect(page.locator(".information-markdown")).toContainText("Browser content.");
  await expect(page.locator("html")).not.toHaveAttribute("data-telegram-fullscreen", "true");
  await expect
    .poll(() =>
      page
        .locator(".information-page-topbar")
        .evaluate((element) => element.getBoundingClientRect().top)
    )
    .toBe(18);
  await page
    .locator(".information-page-topbar")
    .getByRole("link", { name: "Главная", exact: true })
    .click();
  await expect(page.locator(".bottom-nav")).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-telegram-fullscreen", "true");
  expect(sdkLoads).toBe(0);
});

for (const theme of ["dark", "light"] as const) {
  for (const sidebar of [false, true]) {
    test(`document width follows the viewport with sidebar=${sidebar} in ${theme} theme`, async ({
      page,
    }, testInfo) => {
      await page.addInitScript((showInSidebar) => {
        window.sessionStorage.setItem(
          "minishop-demo-documents",
          JSON.stringify([
            {
              title: "Document with a long navigation title and nested path",
              slug: "support/guides/responsive-document",
              role: "none",
              show_in_settings: true,
              show_in_sidebar: false,
              group_title: "Documents",
              sort_order: 0,
              markdown: `# Responsive document\n\n${"LongUnbrokenValue".repeat(30)}\n\n\`\`\`text\n${"Wide code ".repeat(40)}\n\`\`\`\n\n| Item | Value |\n| --- | --- |\n| First | ${"Table value ".repeat(40)} |`,
            },
            {
              title: "Another document",
              slug: "another-document",
              show_in_sidebar: showInSidebar,
              markdown: "Published navigation document",
            },
            {
              title: "Unpublished document",
              slug: "unpublished-document",
              show_in_sidebar: true,
              markdown: " ",
            },
          ])
        );
      }, sidebar);
      await page.setViewportSize({ width: 390, height: 900 });
      await page.goto(
        `/demo/runtime/docs/support/guides/responsive-document?theme_preview=${theme}`
      );
      const layout = page.locator(".information-page-layout");
      const content = page.locator(".information-page-content");
      await expect(page.locator(".information-markdown")).toContainText("Responsive document");
      await expect(page.locator(".information-page-sidebar")).toHaveCount(sidebar ? 1 : 0);

      for (const width of [390, 639, 640, 899, 900, 901, 1023, 1024, 1440, 900, 899, 390]) {
        await page.setViewportSize({ width, height: 900 });
        await expect
          .poll(async () => {
            const layoutBox = await layout.boundingBox();
            const contentBox = await content.boundingBox();
            const sidebarBox = sidebar
              ? await page.locator(".information-page-sidebar").boundingBox()
              : null;
            const gap = await layout.evaluate((element) =>
              Number.parseFloat(getComputedStyle(element).columnGap)
            );
            const expectedWidth =
              layoutBox!.width - (sidebarBox && width >= 900 ? sidebarBox.width + gap : 0);
            return Math.abs(contentBox!.width - expectedWidth);
          })
          .toBeLessThanOrEqual(1);
        expect(
          await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
        ).toBeLessThanOrEqual(1);
        expect(
          await content.evaluate((element) => element.scrollWidth - element.clientWidth)
        ).toBeLessThanOrEqual(1);
        if (width === 900 || width === 1440) {
          await page.screenshot({ path: testInfo.outputPath(`document-${width}.png`) });
        }
      }
    });
  }
}

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
