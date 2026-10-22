import { test, expect, type Page } from "@playwright/test";
import { build } from "esbuild";
import { readFileSync } from "node:fs";
import ru from "../../locales/ru.json";
import en from "../../locales/en.json";
import type { createThemeEffectsRuntime } from "../src/lib/webapp/themeEffectsRuntime";
import type { createThemeEffectHost, ThemeEffectModule } from "../src/lib/webapp/themeEffectsSdk";

declare global {
  interface Window {
    EffectRuntime: { createThemeEffectsRuntime: typeof createThemeEffectsRuntime };
    EffectSdk: { createThemeEffectHost: typeof createThemeEffectHost };
    EffectExample: ThemeEffectModule;
  }
}

async function bundle(file: string, globalName: string) {
  const result = await build({
    entryPoints: [file],
    bundle: true,
    write: false,
    format: "iife",
    globalName,
  });
  return result.outputFiles[0].text;
}

async function installViewerFixture(
  page: Page,
  viewer: { isAdmin: boolean; enabled: boolean; language?: "ru" | "en" }
) {
  const digest = "b".repeat(64);
  const state = {
    requests: 0,
    mergeError: "",
    emailError: "",
    mergeProvider: "telegram",
    confirmRequests: 0,
    cancelRequests: 0,
  };
  await page.route("**/demo/runtime/**", async (route) => {
    if (route.request().resourceType() !== "document") return route.continue();
    const response = await route.fetch();
    const config = {
      title: "Theme effects fixture",
      adminThemeEffectsEnabled: viewer.enabled,
      authProviders: ["telegram", "email", "google", "yandex", "passkey"],
    };
    const body = (await response.text()).replace(
      "</head>",
      `<script id="webapp-config" type="application/json">${JSON.stringify(config)}</script></head>`
    );
    await route.fulfill({ response, body });
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.startsWith("/api/theme-effects/assets/")) {
      if (path.endsWith("/tilt.js"))
        return route.fulfill({
          contentType: "text/javascript",
          body: readFileSync("../examples/theme-effects/tilt/effects/main.js", "utf8"),
        });
      return route.fulfill({
        contentType: "text/javascript",
        body: `import { mount as mountTilt } from './tilt.js';
          export async function mount(host, context) {
            const instance = await mountTilt(host, context);
            document.documentElement.dataset.themeViewerEffect = 'mounted';
            return instance;
          }`,
      });
    }
    let response: Record<string, unknown> = { ok: true };
    if (path === "/api/auth/session")
      response = { ok: true, authenticated: true, csrf_token: "fixture-csrf" };
    if (path.startsWith("/api/i18n")) response = { ok: true, i18n: { ru, en } };
    if (path === "/api/me")
      response = {
        ok: true,
        user: { id: 42, language_code: viewer.language || "ru", is_admin: viewer.isAdmin },
        settings: {
          auth_providers: ["telegram", "email", "google", "yandex", "passkey"],
          email_auth_enabled: true,
        },
        subscription: { active: false },
        plans: [],
        payment_methods: [],
        referral: {},
      };
    if (path === "/api/extensions/runtime") response = { ok: true, generation: 1, plugins: [] };
    if (path === "/api/gifts") response = { ok: true, enabled: false, gifts: [] };
    if (path === "/api/support/tickets")
      response = { ok: true, tickets: [], total: 0, page: 0, pages: 1 };
    if (path === "/api/account/merge/status")
      response = {
        ok: true,
        provider: state.mergeProvider,
        providers: ["google", "telegram", "passkey"],
        target_confirmed: false,
        email_available: true,
        email: "long.account.address@example.com",
      };
    if (path === "/api/account/merge/request") response = { ok: true, email_code: "123456" };
    if (path === "/api/account/email/request") response = { ok: true, email_code: "123456" };
    if (path === "/api/account/email/verify") {
      state.mergeProvider = "email";
      response = state.emailError ? { ok: false, error: state.emailError } : { ok: true };
    }
    if (path === "/api/account/merge/confirm") {
      state.confirmRequests++;
      response = state.mergeError
        ? { ok: false, error: state.mergeError }
        : { ok: true, csrf_token: "fixture-csrf" };
    }
    if (path === "/api/account/merge/cancel") state.cancelRequests++;
    if (path === "/api/theme-effects") {
      state.requests++;
      response = {
        ok: true,
        effect: {
          key: "dark",
          digest,
          effects_digest: digest,
          lease_seconds: 60,
          entry: `/api/theme-effects/assets/dark/${digest}/main.js`,
          styles: [],
          assets: {},
          manifest: {
            api_version: 1,
            runtime: "trusted-dom",
            entry: "main.js",
            description: {},
            targets: ["home.header.surface"],
          },
        },
      };
    }
    await route.fulfill({ json: response });
  });
  return state;
}

for (const viewer of [
  { label: "visitor", isAdmin: false, enabled: false, allowed: true },
  { label: "administrator without consent", isAdmin: true, enabled: false, allowed: false },
  { label: "administrator with consent", isAdmin: true, enabled: true, allowed: true },
]) {
  test(`the app starts theme effects for ${viewer.label} with the real account shape`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    const state = await installViewerFixture(page, viewer);
    await page.goto("/demo/runtime/app/");
    await expect(page.locator(".bottom-nav")).toBeVisible();
    if (viewer.allowed) {
      await expect(page.locator("html")).toHaveAttribute("data-theme-viewer-effect", "mounted");
      expect(state.requests).toBeGreaterThan(0);
    } else {
      await expect(page.locator("html")).not.toHaveAttribute("data-theme-viewer-effect", "mounted");
      expect(state.requests).toBe(0);
    }
    expect(errors).toEqual([]);
  });
}

for (const width of [1280, 390]) {
  for (const language of ["ru", "en"] as const) {
    test(`theme effect control yields to account merge at ${width} in ${language}`, async ({
      page,
    }, testInfo) => {
      await page.setViewportSize({ width, height: 844 });
      const errors: string[] = [];
      page.on("pageerror", (error) => errors.push(error.message));
      const copy = language === "ru" ? ru : en;
      const state = await installViewerFixture(page, { isAdmin: true, enabled: true, language });
      state.mergeError = "account_merge_privileged_source";
      await page.goto("/demo/runtime/app/?external_auth=telegram:account_merge_required");
      const dialog = page.getByRole("dialog", { name: copy.wa_account_merge_title });
      const control = page.locator(".theme-effects-control");
      await expect(dialog).toBeVisible();
      await expect(page.locator("html")).toHaveAttribute("data-theme-viewer-effect", "mounted");
      await expect(page.locator("body")).toHaveAttribute("data-scroll-locked", "");
      await page.screenshot({
        path: testInfo.outputPath(`merge-effects-${width}-${language}.png`),
      });
      await expect(control).toBeHidden();
      const confirm = dialog.getByRole("button", {
        name: copy.wa_account_merge_confirm,
        exact: true,
      });
      await expect(confirm).toBeEnabled();
      await confirm.scrollIntoViewIfNeeded();
      await confirm.click();
      const error = dialog.locator(".status-line.error");
      await expect(error).toHaveText(copy.wa_account_merge_privileged_source);
      await error.scrollIntoViewIfNeeded();
      await expect(error).toBeInViewport();
      await expect(dialog).toBeVisible();
      expect(state.confirmRequests).toBe(1);
      await page.screenshot({
        path: testInfo.outputPath(`merge-protected-${width}-${language}.png`),
      });
      await dialog.locator(".dialog-close-button").click();
      await expect(dialog).toBeHidden();
      await expect(control).toBeVisible();
      expect(state.cancelRequests).toBe(1);
      await expect(page.locator("html")).toHaveAttribute("data-theme-viewer-effect", "mounted");

      state.mergeError = "";
      await page.goto("/demo/runtime/app/?external_auth=telegram:account_merge_required");
      await expect(dialog).toBeVisible();
      await expect(confirm).toBeEnabled();
      await confirm.click();
      await expect(dialog).toContainText(copy.wa_account_merge_done);
      await expect(control).toBeHidden();
      await dialog.getByRole("button", { name: copy.wa_done, exact: true }).click();
      await expect(dialog).toBeHidden();
      await expect(control).toBeVisible();
      expect(state.confirmRequests).toBe(2);
      expect(state.cancelRequests).toBe(1);
      expect(errors).toEqual([]);
    });
  }
}

for (const width of [1280, 390]) {
  test(`administrator can start provider and email linking at ${width}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const state = await installViewerFixture(page, { isAdmin: true, enabled: true });
    const securityUrl = "/demo/runtime/settings/security";
    for (const provider of ["google", "yandex"]) {
      await page.goto(securityUrl);
      await page.route(`**/auth/${provider}/start?*`, (route) => route.fulfill({ body: "" }));
      const request = page.waitForRequest(`**/auth/${provider}/start?*`);
      await page
        .locator(".security-methods .settings-row")
        .filter({ has: page.locator(`[data-provider-logo="${provider}"]`) })
        .click();
      const url = new URL((await request).url());
      expect(url.searchParams.get("purpose")).toBe("link");
      expect(url.searchParams.get("lang")).toBe("ru");
    }

    await page.goto(securityUrl);
    await page.getByRole("button", { name: ru.wa_settings_link_email_action, exact: true }).click();
    const email = page.locator(".webapp-link-email-dialog");
    await email.locator('input[type="email"]').fill("another@example.com");
    await email.getByRole("button", { name: ru.wa_send_code_email, exact: true }).click();
    const code = page.locator(".webapp-link-email-code-dialog");
    await expect(code).toBeVisible();
    await expect(page.locator(".theme-effects-control")).toBeHidden();
    state.emailError = "account_merge_privileged_source";
    await code.getByRole("button", { name: ru.wa_confirm, exact: true }).click();
    await expect(code.locator(".status-line.error")).toHaveText(
      ru.wa_account_merge_privileged_source
    );
    await expect(code).toHaveCSS("opacity", "1");
    await page.screenshot({ path: testInfo.outputPath(`admin-email-link-${width}.png`) });

    state.emailError = "account_merge_required";
    await code.getByRole("button", { name: ru.wa_confirm, exact: true }).click();
    await expect(code).toBeHidden();
    const merge = page.getByRole("dialog", { name: ru.wa_account_merge_title });
    await expect(merge).toBeVisible();
    await expect(merge.locator(".account-merge-source")).toHaveText(
      ru.wa_account_merge_source.replace("{provider}", ru.wa_security_email_source)
    );
    await expect(page.locator(".theme-effects-control")).toBeHidden();
    await merge.locator(".dialog-close-button").click();
    await expect(merge).toBeHidden();
    await expect(page.locator(".theme-effects-control")).toBeVisible();
  });
}

test("runtime disposes listeners, RAF, nodes, styles and late mounts", async ({ page }) => {
  await page.goto("/demo/runtime/app/?theme_effects=off");
  await page.setContent('<div data-theme-effect-target="home.header.surface"></div>');
  await page.addScriptTag({
    content: await bundle("src/lib/webapp/themeEffectsRuntime.ts", "EffectRuntime"),
  });
  const result = await page.evaluate(async () => {
    let events = 0,
      frames = 0,
      disposed = 0;
    const context = { variant: "dark" as const, colors: {}, language: "en", reducedMotion: false };
    const digest = "a".repeat(64);
    const descriptor = {
      key: "sample",
      digest,
      effects_digest: digest,
      lease_seconds: 60,
      entry: `/api/theme-effects/assets/sample/${digest}/main.js`,
      styles: [],
      assets: {},
      manifest: {
        api_version: 1 as const,
        runtime: "trusted-dom" as const,
        entry: "main.js",
        description: {},
        targets: ["home.header.surface" as const],
      },
    };
    const module: ThemeEffectModule = {
      mount(host) {
        const node = document.createElement("canvas");
        host.targets("home.header.surface")[0].append(node);
        host.listen(window, "test-effect", () => events++);
        host.animation(() => frames++);
        return {
          update() {},
          dispose() {
            disposed++;
          },
        };
      },
    };
    const runtime = window.EffectRuntime.createThemeEffectsRuntime(async () => module);
    await runtime.start(descriptor, context);
    window.dispatchEvent(new Event("test-effect"));
    await new Promise(requestAnimationFrame);
    await runtime.dispose();
    const before = frames;
    window.dispatchEvent(new Event("test-effect"));
    await new Promise(requestAnimationFrame);
    let finish: ((value: Awaited<ReturnType<ThemeEffectModule["mount"]>>) => void) | undefined;
    const late = window.EffectRuntime.createThemeEffectsRuntime(async () => ({
      mount() {
        return new Promise((resolve) => {
          finish = resolve;
        });
      },
    }));
    const starting = late.start(descriptor, context);
    while (!finish) await new Promise((resolve) => setTimeout(resolve, 0));
    await late.dispose();
    finish({
      update() {},
      dispose() {
        disposed++;
      },
    });
    await starting;
    return {
      events,
      stopped: before === frames,
      disposed,
      canvases: document.querySelectorAll("canvas").length,
    };
  });
  expect(result).toEqual({ events: 1, stopped: true, disposed: 2, canvases: 0 });
});

for (const width of [1280, 390]) {
  test(`administrator theme effects setting persists at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/demo/runtime/app/?screen=admin&admin_section=appearance");
    await page.locator(".appearance-preferences-trigger").click();
    const toggle = page.getByRole("switch", {
      name: "JavaScript темы для администраторов",
      exact: true,
    });
    const save = page
      .locator(".appearance-action-bar")
      .getByRole("button", { name: "Сохранить", exact: true });
    await expect(toggle).not.toBeChecked();
    await toggle.click();
    await save.click();
    await expect(page.locator(".appearance-unsaved-note")).toBeHidden();
    await page.reload();
    await page.locator(".appearance-preferences-trigger").click();
    await expect(toggle).toBeChecked();
    await toggle.scrollIntoViewIfNeeded();
    await expect(toggle).toBeInViewport();
    await page.screenshot({
      path: testInfo.outputPath(`admin-effects-${width}.png`),
      fullPage: true,
    });
    await toggle.click();
    await save.click();
    await expect(page.locator(".appearance-unsaved-note")).toBeHidden();
    await page.reload();
    await page.locator(".appearance-preferences-trigger").click();
    await expect(toggle).not.toBeChecked();
  });

  test(`theme consent dialogs at ${width}`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/demo/runtime/app/?screen=admin&admin_section=appearance");
    const library = page.locator(".appearance-library");
    await library.getByRole("button", { name: "Добавить темы", exact: true }).click();
    const dialog = page.locator(".appearance-import-dialog");
    await dialog.locator('input[type="file"]').setInputFiles("../examples/theme-effects/tilt.zip");
    const consent = dialog.locator(".effects-consent");
    await expect(consent).toContainText("читать данные страницы");
    await expect(consent.getByRole("checkbox")).not.toBeChecked();
    await page.screenshot({ path: testInfo.outputPath(`consent-${width}.png`), fullPage: true });
    await dialog.getByRole("button", { name: /Установить/ }).click();
    await expect(dialog).toBeHidden();
    const card = library.locator('[data-theme-key="tilt"]');
    await card.getByRole("button", { name: "JavaScript выключен", exact: true }).click();
    const settings = page.getByRole("dialog").filter({ has: page.locator(".effects-consent") });
    const enable = settings.getByRole("button", { name: "Разрешить эффекты", exact: true });
    await expect(enable).toBeDisabled();
    await settings.locator(".effects-consent").getByRole("checkbox").check();
    await expect(enable).toBeEnabled();
    await expect
      .poll(async () => (await settings.locator(".dialog-card").boundingBox())?.y ?? -1)
      .toBeGreaterThanOrEqual(0);
    await expect(
      settings.getByRole("heading", { name: "Эффекты JavaScript", exact: true })
    ).toBeInViewport();
    await page.screenshot({ path: testInfo.outputPath(`settings-${width}.png`), fullPage: true });
    await enable.click();
    await expect(
      card.getByRole("button", { name: "JavaScript включён", exact: true })
    ).toBeVisible();
  });

  test(`Tilt adapter mounts and releases its layers at ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/demo/runtime/app/?theme_effects=off");
    await page.setContent(
      '<main style="width:320px;background:#142438;padding:20px"><div data-theme-effect-target="home.header.surface" style="width:300px;height:200px"></div></main>'
    );
    await page.addScriptTag({
      content: await bundle("src/lib/webapp/themeEffectsSdk.ts", "EffectSdk"),
    });
    await page.addScriptTag({
      content: await bundle("../examples/theme-effects-src/tilt.ts", "EffectExample"),
    });
    const result = await page.evaluate(async () => {
      const scope = window.EffectSdk.createThemeEffectHost(["home.header.surface"], {});
      const instance = await window.EffectExample.mount(scope.host, {
        variant: "dark",
        colors: {},
        language: "en",
        reducedMotion: false,
      });
      const layers = document.querySelectorAll("[data-theme-effect-target] > div").length;
      await instance.dispose();
      scope.dispose();
      return {
        layers,
        remaining: document.querySelectorAll("[data-theme-effect-target] > div").length,
      };
    });
    expect(result).toEqual({ layers: 1, remaining: 0 });
  });
}

test("prebuilt example contains the ESM lifecycle exports", () => {
  const script = readFileSync("../examples/theme-effects/tilt/effects/main.js", "utf8");
  expect(script).toContain("export{");
  expect(script).not.toContain("html2canvas");
});
