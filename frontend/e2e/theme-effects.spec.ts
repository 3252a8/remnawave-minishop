import { test, expect } from "@playwright/test";
import { build } from "esbuild";
import { readFileSync } from "node:fs";
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
