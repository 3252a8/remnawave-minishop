import { expect, test, type Page } from "@playwright/test";

const emojiIds = {
  image: "5368324170671202286",
  decode: "5368324170671202287",
  unavailable: "5368324170671202288",
  unsafe: "5368324170671202289",
};
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/lwsAAAAASUVORK5CYII=",
  "base64"
);

declare global {
  interface Window {
    supportEmojiMediaUrls: { created: string[]; revoked: string[] };
  }
}

async function installFixture(
  page: Page,
  admin: boolean,
  paging: { holdNextPage?: boolean; failNextPage?: boolean } | null = null
) {
  const requestedMedia: string[] = [];
  const unsafeRequests: string[] = [];
  const errors: string[] = [];
  const catalogRequests: { offset: number; q: string }[] = [];
  let releaseNextPage = () => {};
  const nextPageReleased = new Promise<void>((resolve) => {
    releaseNextPage = resolve;
  });
  let markNextPageHandled = () => {};
  const nextPageHandled = new Promise<void>((resolve) => {
    markNextPageHandled = resolve;
  });
  let failedNextPage = false;
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (request.url().startsWith("https://evil.test/")) unsafeRequests.push(request.url());
  });
  await page.addInitScript(() => {
    window.supportEmojiMediaUrls = { created: [], revoked: [] };
    const create = URL.createObjectURL.bind(URL);
    const revoke = URL.revokeObjectURL.bind(URL);
    URL.createObjectURL = (blob) => {
      const url = create(blob);
      window.supportEmojiMediaUrls.created.push(url);
      return url;
    };
    URL.revokeObjectURL = (url) => {
      window.supportEmojiMediaUrls.revoked.push(url);
      revoke(url);
    };
  });
  await page.route("**/demo/runtime/**", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const body = (await response.text()).replace(
      "</head>",
      '<script id="webapp-config" type="application/json">{"title":"Support emoji fixture"}</script></head>'
    );
    return route.fulfill({ response, body });
  });
  const ticket = {
    ticket_id: 7,
    user_id: 42,
    subject: "Emoji fixture",
    category: "other",
    priority: "normal",
    status: "open",
    unread_user_count: 0,
    unread_admin_count: 0,
    user: { id: 42, first_name: "Customer", username: "customer" },
  };
  const emoji = (id: string, fallback: string) =>
    `<tg-emoji emoji-id="${id}">${fallback}</tg-emoji>`;
  const body = `<b>${emoji(emojiIds.image, "👩🏽‍💻")}</b> ${emoji(emojiIds.decode, "🙂")} ${emoji(emojiIds.unavailable, "❤️")} ${emoji(emojiIds.unsafe, "🌈")} <a href="https://example.test/help">help</a> <img src="https://evil.test/tracker" onerror="alert(1)"> <tg-emoji emoji-id="../secret">🙂</tg-emoji> <code>${emoji(emojiIds.image, "☀️")}</code>`;
  const messages = ["user", "admin"].map((role, index) => ({
    message_id: index + 1,
    ticket_id: 7,
    author_role: role,
    author_name: role === "admin" ? "Support" : "Customer",
    body,
    body_format: "html",
    is_internal_note: false,
    image_id: null,
    buttons: [
      {
        label: "Custom button",
        url: "https://example.test/custom",
        icon_custom_emoji_id: emojiIds.image,
        icon_emoji: "👩🏽‍💻",
      },
      { label: "Unicode button", url: "https://example.test/unicode", icon_emoji: "🚀" },
    ],
    created_at: "2026-10-04T10:00:00Z",
  }));
  await page.route("**/api/**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const path = requestUrl.pathname;
    const media = path.match(
      /^\/api\/(?:admin\/telegram-emoji\/media|support\/tickets\/7\/emoji)\/([1-9][0-9]*)$/
    );
    if (media) {
      requestedMedia.push(path);
      if (media[1] === emojiIds.unavailable)
        return route.fulfill({
          status: 503,
          json: { ok: false, error: "telegram_emoji_unavailable" },
        });
      if (media[1] === emojiIds.unsafe)
        return route.fulfill({ contentType: "image/svg+xml", body: '<svg onload="alert(1)" />' });
      return route.fulfill({
        contentType: "image/png",
        body: media[1] === emojiIds.decode ? Buffer.from("invalid image") : png,
      });
    }
    let response: Record<string, unknown> = { ok: true };
    if (path === "/api/admin/me") response = { ok: true, user_id: 42 };
    if (paging && path === "/api/admin/telegram-emoji/library")
      response = {
        ok: true,
        library: { schema_version: 1, sets: ["fixture"], manual_ids: [] },
        revision: "fixture",
        sets: [{ name: "fixture", title: "Fixture", count: 120, state: "ready" }],
      };
    if (paging && path === "/api/admin/telegram-emoji/catalog") {
      const offset = Number(requestUrl.searchParams.get("offset") || 0);
      const q = requestUrl.searchParams.get("q") || "";
      catalogRequests.push({ offset, q });
      if (offset > 0 && !q && paging.holdNextPage) await nextPageReleased;
      if (offset > 0 && !q && paging.failNextPage && !failedNextPage) {
        failedNextPage = true;
        return route.fulfill({
          status: 503,
          json: { ok: false, error: "telegram_emoji_load_failed" },
        });
      }
      const items = Array.from({ length: 120 }, (_, index) => ({
        id: String(BigInt(emojiIds.image) + BigInt(index)),
        fallback: index % 2 ? "💎" : "🚀",
        set_name: "fixture",
        thumbnail_url: null,
        format: "static",
      })).filter((item) => !q || item.fallback.includes(q));
      response = {
        ok: true,
        items: items.slice(offset, offset + 60),
        total: items.length,
        offset,
        limit: 60,
      };
    }
    if (path === "/api/auth/session")
      response = { ok: true, authenticated: true, csrf_token: "fixture-csrf" };
    if (path.startsWith("/api/i18n")) response = { ok: true, i18n: { ru: {}, en: {} } };
    if (path === "/api/me")
      response = {
        ok: true,
        user: { id: 42, language_code: "ru", is_admin: admin, first_name: "Customer" },
        settings: { support_tickets_enabled: true },
        subscription: { active: false },
        plans: [],
        payment_methods: [],
        referral: {},
      };
    if (path === "/api/extensions/runtime") response = { ok: true, generation: 1, plugins: [] };
    if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
    if (/^\/api\/(?:admin\/)?support\/tickets$/.test(path))
      response = { ok: true, tickets: [ticket], total: 1, page: 0, pages: 1, counts: { total: 1 } };
    if (/^\/api\/(?:admin\/)?support\/tickets\/7$/.test(path))
      response = { ok: true, ticket, messages, user_snapshot: ticket.user, peer_typing: false };
    if (path === "/api/admin/support/stats")
      response = { ok: true, stats: { active: 1, total: 1 } };
    if (path === "/api/support/unread") response = { ok: true, unread: 0 };
    try {
      await route.fulfill({ json: response });
    } finally {
      if (
        paging?.holdNextPage &&
        path === "/api/admin/telegram-emoji/catalog" &&
        Number(requestUrl.searchParams.get("offset")) > 0
      )
        markNextPageHandled();
    }
  });
  return {
    requestedMedia,
    unsafeRequests,
    errors,
    catalogRequests,
    releaseNextPage,
    nextPageHandled,
  };
}

for (const admin of [false, true]) {
  test(`${admin ? "admin" : "Web App"} support renders authenticated custom emoji and preserves safe fallback`, async ({
    page,
  }) => {
    const fixture = await installFixture(page, admin);
    await page.setViewportSize(admin ? { width: 1280, height: 900 } : { width: 390, height: 844 });
    await page.goto(`/demo/runtime/${admin ? "admin/" : ""}support/7`);
    const conversation = page.locator(admin ? ".support-admin-messages" : ".ticket-message-list");
    const messages = conversation.locator(".ticket-message-text");
    await expect(messages).toHaveCount(2);
    await expect(conversation.locator(".ticket-message-row--incoming")).toHaveCount(1);
    await expect(conversation.locator(".ticket-message-row--outgoing")).toHaveCount(1);

    for (const message of await messages.all()) {
      const wrapper = message.locator(`[data-custom-emoji-id="${emojiIds.image}"]`);
      const image = wrapper.locator("img");
      await expect(image).toBeVisible();
      await expect(image).toHaveAttribute("src", /^blob:/);
      await expect(image).toHaveAttribute("alt", "");
      await expect(image).toHaveAttribute("aria-hidden", "true");
      await expect(wrapper.locator(".rt-custom-emoji-fallback")).toHaveCSS("opacity", "0");
      await expect(message.locator(`b > [data-custom-emoji-id="${emojiIds.image}"]`)).toHaveCount(
        1
      );
      await expect(message.getByRole("link", { name: "help", exact: true })).toHaveAttribute(
        "href",
        "https://example.test/help"
      );
      await expect(message.locator("code")).toHaveText("☀️");
      await expect(message.locator("tg-emoji")).toHaveCount(0);
      await expect(message.locator('img[src^="https:"]')).toHaveCount(0);
      for (const id of [emojiIds.decode, emojiIds.unavailable, emojiIds.unsafe]) {
        const fallback = message.locator(`[data-custom-emoji-id="${id}"]`);
        await expect(fallback.locator(".rt-custom-emoji-fallback")).toHaveCSS("opacity", "1");
        await expect(fallback.locator("img")).toBeHidden();
        await expect(fallback.locator("img")).not.toHaveAttribute("src", /.+/);
      }
      expect(
        await wrapper.evaluate((element) => {
          const range = document.createRange();
          range.selectNodeContents(element);
          const selection = window.getSelection();
          selection?.removeAllRanges();
          selection?.addRange(range);
          return selection?.toString();
        })
      ).toBe("👩🏽‍💻");
    }
    for (const row of await conversation.locator(".ticket-message-row").all()) {
      const customButton = row.getByRole("link", { name: "Custom button", exact: true });
      await customButton.scrollIntoViewIfNeeded();
      await expect(customButton.locator("img")).toBeVisible();
      await expect(customButton.locator("img")).toHaveAttribute("src", /^blob:/);
      const ordinaryButton = row.getByRole("link", { name: "Unicode button", exact: true });
      await expect(ordinaryButton).toBeVisible();
      await expect(ordinaryButton.locator(".emoji-glyph")).toHaveText("🚀");
    }
    const prefix = admin ? "/api/admin/telegram-emoji/media/" : "/api/support/tickets/7/emoji/";
    expect(new Set(fixture.requestedMedia).size).toBe(4);
    expect(fixture.requestedMedia.filter((path) => path.endsWith(emojiIds.image))).toHaveLength(1);
    expect(fixture.requestedMedia.every((path) => path.startsWith(prefix))).toBe(true);
    expect(fixture.unsafeRequests).toEqual([]);
    expect(fixture.errors).toEqual([]);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    ).toBeLessThanOrEqual(2);
    if (admin) await page.keyboard.press("Escape");
    else await page.locator(".support-back-button").click();
    await expect(messages).toHaveCount(0);
    const urls = await page.evaluate(() => window.supportEmojiMediaUrls);
    expect(urls.created).toHaveLength(6);
    expect(urls.created.every((url) => urls.revoked.includes(url))).toBe(true);
  });
}

async function openButtonEmojiPicker(page: Page) {
  await page.goto("/demo/runtime/admin/support/7");
  await page
    .locator(".support-admin-composer-buttons")
    .getByRole("button", { name: /Add button|Добавить кнопку/ })
    .click();
  await page.locator(".message-button-emoji-trigger").click();
  const dialog = page.locator(".telegram-emoji-dialog");
  await expect(dialog.locator(".picker-tabs button").first()).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await dialog.locator(".picker-tabs button").nth(1).click();
  await expect(dialog.locator(".picker-cell")).toHaveCount(60);
  return dialog;
}

test("emoji catalog automatically loads in the dialog and discards a page after search changes", async ({
  page,
}) => {
  const fixture = await installFixture(page, true, { holdNextPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openButtonEmojiPicker(page);
  const viewport = dialog.locator(".dialog-body-scroll .scroll-area__viewport");
  await expect(dialog.locator(".picker-pagination button")).toHaveCount(0);
  await viewport.evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect
    .poll(() => fixture.catalogRequests.some(({ offset, q }) => offset === 60 && !q))
    .toBe(true);
  await dialog.locator('input[type="search"]').fill("💎");
  await expect(dialog.locator(".picker-cell")).toHaveCount(60);
  await expect(dialog.locator(".picker-cell").first()).toHaveAttribute("aria-label", /^💎 /);
  fixture.releaseNextPage();
  await fixture.nextPageHandled;
  await expect(dialog.locator(".picker-cell")).toHaveCount(60);
  await expect(dialog.locator('.picker-cell[aria-label^="🚀 "]')).toHaveCount(0);
  await expect(viewport).toBeInViewport();
  expect(
    await dialog.evaluate((element) => element.scrollWidth - element.clientWidth)
  ).toBeLessThanOrEqual(2);
  expect(fixture.errors).toEqual([]);
});

test("support button icons choose Unicode/custom, clear, restore focus and serialize without changing captions", async ({
  page,
}) => {
  const fixture = await installFixture(page, true, {});
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/demo/runtime/admin/support/7");
  const composer = page.locator(".support-admin-composer");
  const add = composer.getByRole("button", { name: /Add button|Добавить кнопку/ });
  await add.click();
  const rows = composer.locator(".message-button-row");
  const customRow = rows.first();
  await customRow.locator(".message-button-caption").fill("Plain custom caption");
  await customRow.locator(".message-button-target").fill("https://example.test/custom");
  const trigger = customRow.locator(".message-button-emoji-trigger");
  await trigger.click();
  const dialog = page.locator(".telegram-emoji-dialog");
  await expect(dialog.locator(".picker-tabs button").first()).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await dialog.locator('.picker-cell[aria-label^="🚀 "]').click();
  await dialog.locator(".picker-footer-actions button").last().click();
  await expect(trigger).toBeFocused();
  await expect(customRow.locator(".message-button-caption")).toHaveValue("Plain custom caption");
  await expect(trigger.locator(".emoji-glyph")).toHaveText("🚀");
  await customRow.locator(".message-button-emoji > button").nth(1).click();
  await expect(trigger.locator(".emoji-glyph")).toHaveCount(0);
  await trigger.click();
  await dialog.locator(".picker-tabs button").nth(1).click();
  await dialog.locator(".picker-cell").first().click();
  await dialog.locator(".picker-footer-actions button").last().click();
  await expect(trigger).toBeFocused();
  await trigger.click();
  await expect(dialog.locator(".picker-tabs button").nth(1)).toHaveAttribute(
    "aria-pressed",
    "true"
  );
  await page.keyboard.press("Escape");
  await expect(trigger).toBeFocused();
  await add.click();
  const ordinaryRow = rows.nth(1);
  await ordinaryRow.locator(".message-button-caption").fill("Plain ordinary caption");
  await ordinaryRow.locator(".message-button-target").fill("https://example.test/ordinary");
  await ordinaryRow.locator(".message-button-emoji-trigger").click();
  await dialog.locator('.picker-cell[aria-label^="❤️ "]').click();
  await dialog.locator(".picker-footer-actions button").last().click();
  await composer.locator('[contenteditable="true"]').fill("Hello");
  const requestPromise = page.waitForRequest(
    (request) =>
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/admin/support/tickets/7/messages"
  );
  await composer
    .locator(".support-admin-composer-actions")
    .getByRole("button", { name: /Send|Отправить/ })
    .click();
  const payload = (await requestPromise).postDataJSON();
  expect(payload.buttons).toEqual([
    expect.objectContaining({
      label: "Plain custom caption",
      icon_custom_emoji_id: emojiIds.image,
      icon_emoji: "🚀",
    }),
    expect.objectContaining({
      label: "Plain ordinary caption",
      icon_custom_emoji_id: null,
      icon_emoji: "❤️",
    }),
  ]);
  expect(fixture.errors).toEqual([]);
});

test("emoji pagination preserves loaded results after failure and retries only on request", async ({
  page,
}) => {
  const fixture = await installFixture(page, true, { failNextPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  const dialog = await openButtonEmojiPicker(page);
  await dialog.locator(".dialog-body-scroll .scroll-area__viewport").evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await expect(dialog.locator(".picker-error[role=alert]")).toBeVisible();
  await expect(dialog.locator(".picker-cell")).toHaveCount(60);
  expect(fixture.catalogRequests.filter(({ offset }) => offset === 60)).toHaveLength(1);
  await dialog.locator(".picker-pagination button").click();
  await expect(dialog.locator(".picker-cell")).toHaveCount(120);
  await expect(dialog.locator(".picker-error[role=alert]")).toHaveCount(0);
  expect(fixture.catalogRequests.filter(({ offset }) => offset === 60)).toHaveLength(2);
  expect(fixture.errors).toEqual([]);
});
