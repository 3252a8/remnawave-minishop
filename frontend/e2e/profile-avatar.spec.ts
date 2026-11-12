import { expect, test, type Route } from "@playwright/test";

const primaryUrl = "/api/account/avatar";
const fallbackUrl = "https://avatar.example.test/telegram-photo.png";
const avatarImage = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a7WQAAAAASUVORK5CYII=",
  "base64"
);

function fulfillAvatar(route: Route, status: number) {
  return status === 200
    ? route.fulfill({ contentType: "image/png", body: avatarImage })
    : route.fulfill({ status, contentType: "text/plain", body: "avatar_not_cached" });
}

for (const { name, width, primaryStatus, fallbackStatus, expectedUrl } of [
  {
    name: "cached photo",
    width: 1440,
    primaryStatus: 200,
    fallbackStatus: 200,
    expectedUrl: primaryUrl,
  },
  {
    name: "saved Telegram photo",
    width: 390,
    primaryStatus: 404,
    fallbackStatus: 200,
    expectedUrl: fallbackUrl,
  },
  { name: "profile icon with no saved photo", width: 1440, primaryStatus: 404 },
  {
    name: "profile icon when both photos fail",
    width: 390,
    primaryStatus: 500,
    fallbackStatus: 404,
  },
]) {
  test(`settings show the ${name} at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route("**/settings?**", async (route) => {
      if (route.request().resourceType() !== "document") return route.continue();
      const response = await route.fetch();
      const config = { authProviders: ["telegram"], emailAuthEnabled: false };
      const body = (await response.text()).replace(
        "</head>",
        `<script id="webapp-config" type="application/json">${JSON.stringify(config)}</script></head>`
      );
      await route.fulfill({ response, body });
    });
    let fallbackRequests = 0;
    await page.route(fallbackUrl, (route) => {
      fallbackRequests += 1;
      return fulfillAvatar(route, fallbackStatus ?? 200);
    });
    await page.route("**/api/**", async (route) => {
      switch (new URL(route.request().url()).pathname) {
        case primaryUrl:
          return fulfillAvatar(route, primaryStatus);
        case "/api/auth/session":
          return route.fulfill({ json: { ok: true, authenticated: true, csrf_token: "test" } });
        case "/api/me":
          return route.fulfill({
            json: {
              ok: true,
              user: {
                id: 42,
                first_name: "Alex",
                telegram_id: 42,
                telegram_linked: true,
                telegram_photo_url: primaryUrl,
                telegram_photo_fallback_url: fallbackStatus ? fallbackUrl : "",
              },
              settings: {},
              subscription: { active: false },
              plans: [],
              payment_methods: [],
              referral: {},
            },
          });
        default:
          return route.fulfill({ json: { ok: true } });
      }
    });

    await page.goto("/settings?theme_preview=dark");
    const avatar = page.locator(".settings-avatar");
    const image = avatar.locator("img");
    if (expectedUrl) {
      await expect(image).toHaveAttribute("src", expectedUrl);
      await expect
        .poll(() => image.evaluate((element: HTMLImageElement) => element.naturalWidth))
        .toBe(1);
    } else {
      await expect(avatar.locator("svg")).toBeVisible();
      await expect(image).toHaveCount(0);
    }
    expect(fallbackRequests).toBe(fallbackStatus && expectedUrl !== primaryUrl ? 1 : 0);
  });
}
