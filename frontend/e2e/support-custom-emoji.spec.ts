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

async function installFixture(page: Page, admin: boolean) {
  const requestedMedia: string[] = [];
  const unsafeRequests: string[] = [];
  const errors: string[] = [];
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
    buttons: [],
    created_at: "2026-10-04T10:00:00Z",
  }));
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
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
    await route.fulfill({ json: response });
  });
  return { requestedMedia, unsafeRequests, errors };
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
    const prefix = admin ? "/api/admin/telegram-emoji/media/" : "/api/support/tickets/7/emoji/";
    expect(fixture.requestedMedia).toHaveLength(8);
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
    expect(urls.created).toHaveLength(4);
    expect(urls.created.every((url) => urls.revoked.includes(url))).toBe(true);
  });
}
