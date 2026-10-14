import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const CODE = "AbCdEfGhIjKlMnOpQr_s-t";
const REQUEST_ID = "Z".repeat(22);
const locales = {
  ru: JSON.parse(readFileSync("../locales/ru.json", "utf8")),
  en: JSON.parse(readFileSync("../locales/en.json", "utf8")),
};

async function configure(page: Page, authenticated: boolean, language: "ru" | "en") {
  await page.route("**/demo/runtime/**", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const config = { authProviders: ["qr"], emailAuthEnabled: false, defaultLanguage: language };
    const body = (await response.text()).replace(
      "</head>",
      `<script id="webapp-config" type="application/json">${JSON.stringify(config)}</script></head>`
    );
    await route.fulfill({ response, body });
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let response: Record<string, unknown> = { ok: true };
    if (path === "/api/auth/session") response = { ok: true, authenticated, csrf_token: "test" };
    if (path.startsWith("/api/i18n")) response = { ok: true, i18n: locales };
    if (path === "/api/me")
      response = {
        ok: true,
        user: { id: 42, language_code: language, is_admin: false },
        settings: { authProviders: ["qr"], public_url: "https://shop.example" },
        subscription: { active: false },
        plans: [],
        payment_methods: [],
        referral: {},
      };
    if (path === "/api/extensions/runtime") response = { ok: true, generation: 1, plugins: [] };
    if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
    if (path === "/api/auth/qr/start")
      response = {
        ok: true,
        request_id: REQUEST_ID,
        qr_url: `https://shop.example/settings#qrlogin=${CODE}`,
        expires_in: 120,
        poll_interval: 1,
      };
    if (path === "/api/auth/qr/poll")
      response = { ok: true, status: "scanned", match_number: 42, expires_in: 120 };
    if (path === "/api/account/qr-login/claim")
      response = {
        ok: true,
        request_id: REQUEST_ID,
        browser: "Firefox",
        os: "Linux",
        ip: "203.0.113.5",
        expires_in: 120,
      };
    if (path === "/api/account/qr-login/approve") response = { ok: true, status: "approved" };
    await route.fulfill({ json: response });
  });
}

for (const [device, viewport] of [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
] as const) {
  for (const language of ["ru", "en"] as const) {
    test(`QR sign-in dialogs work on ${device} in ${language}`, async ({ page }, testInfo) => {
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      await page.setViewportSize(viewport);
      await configure(page, false, language);
      await page.goto("/demo/runtime/login?theme_preview=dark");
      await page.locator('[data-auth-provider="qr"]').click();
      const waiting = page.locator(".qr-login-dialog");
      await expect(waiting.locator(".link-qr-tile img")).toBeVisible();
      await waiting.screenshot({ path: testInfo.outputPath(`qr-code-${device}-${language}.png`) });
      await expect(waiting.locator(".qr-login-number")).toHaveText("42");
      const cancel = page.waitForRequest("**/api/auth/qr/cancel");
      await page.keyboard.press("Escape");
      expect((await cancel).postDataJSON()).toEqual({ request_id: REQUEST_ID });
      await expect(waiting).toBeHidden();

      await configure(page, true, language);
      await page.goto(`/demo/runtime/settings?theme_preview=dark#qrlogin=${CODE}`);
      const approval = page.locator(".qr-approve-dialog");
      await expect(approval).toContainText("Firefox · Linux");
      await expect(approval).toContainText("203.0.113.5");
      expect(new URL(page.url()).hash).toBe("");
      expect(
        await approval.evaluate((node) => node.scrollWidth - node.clientWidth)
      ).toBeLessThanOrEqual(2);
      await approval.screenshot({
        path: testInfo.outputPath(`qr-approval-${device}-${language}.png`),
      });
      const confirm = approval.locator(".qr-approve-actions button").last();
      await expect(confirm).toBeDisabled();
      await approval.locator("input").fill("42");
      const approve = page.waitForRequest("**/api/account/qr-login/approve");
      await confirm.click();
      expect((await approve).postDataJSON()).toEqual({ request_id: REQUEST_ID, number: 42 });
      await expect(approval.locator("input")).toHaveCount(0);
      await expect(approval.locator(".dialog-close-button")).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(approval).toBeHidden();
      expect(errors).toEqual([]);
    });
  }
}

test("closing and reopening the scanner stops a camera granted to the old dialog", async ({
  page,
}) => {
  await configure(page, true, "ru");
  await page.addInitScript(() => {
    const state = { pending: [] as (() => void)[], stopped: 0 };
    Object.assign(window, { qrCamera: state });
    Object.defineProperty(navigator.mediaDevices, "getUserMedia", {
      value: () =>
        new Promise<MediaStream>((resolve) => {
          state.pending.push(() => {
            const stream = new MediaStream();
            stream.getTracks = () =>
              [
                {
                  stop: () => {
                    state.stopped += 1;
                  },
                },
              ] as MediaStreamTrack[];
            resolve(stream);
          });
        }),
    });
  });
  await page.goto("/demo/runtime/settings?theme_preview=dark");
  const scan = page.locator('[data-webapp-action="scan-qr-login"]');
  await expect(scan).toContainText("shop.example");
  await scan.click();
  await expect(page.locator(".qr-scan-dialog")).toBeVisible();
  const state = () =>
    page.evaluate(
      () =>
        (
          window as unknown as {
            qrCamera: { pending: (() => void)[]; stopped: number };
          }
        ).qrCamera.pending.length
    );
  await expect.poll(state).toBe(1);
  await page.keyboard.press("Escape");
  await scan.click();
  await expect.poll(state).toBe(2);
  await page.evaluate(() =>
    (
      window as unknown as {
        qrCamera: { pending: (() => void)[] };
      }
    ).qrCamera.pending[0]()
  );
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          (
            window as unknown as {
              qrCamera: { stopped: number };
            }
          ).qrCamera.stopped
      )
    )
    .toBe(1);
  await expect(page.locator(".qr-scan-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
});
