/* global document, window, Image, OffscreenCanvas */

// Capture every customer-cabinet and admin screen of the docs demo on desktop
// and mobile, with an HTML gallery and optional before/after comparison.
//
//   npm --prefix frontend run screens -- --out ../ui-shots/before
//   npm --prefix frontend run screens -- --out ../ui-shots/after --baseline ../ui-shots/before
//
// See scripts/ui-screens/README.md for all options.

import { chromium } from "@playwright/test";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import { demoAdminRoutes } from "../../../docs-site/src/lib/demoRoutes.mjs";
import { renderGallery } from "./gallery.mjs";
import { THEMES, VIEWPORTS, staticScreens } from "./manifest.mjs";
import {
  FREEZE_CSS,
  auditLayout,
  discoverVariants,
  measureOverflow,
  waitForQuietDom,
} from "./page-probes.mjs";
import { serveDemo } from "./server.mjs";

const frontendRoot = path.resolve(fileURLToPath(new URL("../..", import.meta.url)));
const repoRoot = path.resolve(frontendRoot, "..");
const publicRoot = path.join(repoRoot, "docs-site", "public");
const RUNTIME = "/demo/runtime";
const MAX_HEIGHT = 8000;
const FIXED_NOW = "2026-05-28T09:00:00Z";

const { values: args } = parseArgs({
  options: {
    out: { type: "string" },
    base: { type: "string" },
    port: { type: "string" },
    build: { type: "boolean", default: false },
    only: { type: "string" },
    viewports: { type: "string", default: "desktop,mobile" },
    themes: { type: "string", default: THEMES.join(",") },
    format: { type: "string", default: "webp" },
    quality: { type: "string", default: "82" },
    concurrency: { type: "string", default: "4" },
    baseline: { type: "string" },
    now: { type: "string", default: FIXED_NOW },
    list: { type: "boolean", default: false },
    "no-audit": { type: "boolean", default: false },
    "no-discover": { type: "boolean", default: false },
    help: { type: "boolean", short: "h", default: false },
  },
});

if (args.help) {
  console.log(`Usage: node scripts/ui-screens/ui-screens.mjs [options]
  --out <dir>          output directory (default: test-results/ui-screens/<timestamp>)
  --base <url>         use a running demo origin instead of serving docs-site/public
  --port <number>      local demo port (defaults to the baseline's port when comparing)
  --build              rebuild the docs demo before capturing
  --only <regex>       capture only screen ids matching the expression
  --viewports <list>   ${Object.keys(VIEWPORTS).join(",")} (default: desktop,mobile)
  --themes <list>      ${THEMES.join(",")} (default: all)
  --format webp|png    image format (default: webp)
  --quality <1-100>    webp quality (default: 82)
  --concurrency <n>    parallel browser contexts (default: 4)
  --baseline <dir>     previous run: gallery shows before/after and changed shots
  --now <iso|real>     frozen clock for stable dates (default: ${FIXED_NOW})
  --list               print the expanded plan without capturing
  --no-audit           skip the layout heuristics
  --no-discover        do not expand tabs and accordion groups`);
  process.exit(0);
}

const viewports = args.viewports.split(",").map((name) => name.trim());
const themes = args.themes.split(",").map((name) => name.trim());
for (const name of viewports) {
  if (!VIEWPORTS[name]) throw new Error(`unknown viewport: ${name}`);
}
if (!["webp", "png"].includes(args.format)) throw new Error("--format must be webp or png");
const onlyPattern = args.only ? new RegExp(args.only) : null;
const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, "");
// npm runs the script from frontend/; relative paths mean the caller's directory.
const callerDir = process.env.INIT_CWD || process.cwd();
const outDir = args.out
  ? path.resolve(callerDir, args.out)
  : path.join(frontendRoot, "test-results", "ui-screens", stamp);

function run(command, commandArgs, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, commandArgs, {
      cwd,
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    child.on("error", reject);
    child.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${command} exited with ${code}`))
    );
  });
}

async function newContext(browser, viewportName, theme) {
  const viewport = VIEWPORTS[viewportName];
  const context = await browser.newContext({
    viewport: { width: viewport.width, height: viewport.height },
    deviceScaleFactor: viewport.scale,
    hasTouch: viewport.touch,
    locale: "ru-RU",
    timezoneId: "Europe/Moscow",
    colorScheme: theme === "light" ? "light" : "dark",
    reducedMotion: "reduce",
  });
  await context.addInitScript((css) => {
    const inject = () => {
      const style = document.createElement("style");
      style.dataset.uiScreens = "freeze";
      style.textContent = css;
      document.head.append(style);
    };
    if (document.head) inject();
    else document.addEventListener("DOMContentLoaded", inject, { once: true });
  }, FREEZE_CSS);
  return context;
}

function screenUrl(origin, screen, theme) {
  const url = new URL(origin + RUNTIME + screen.url);
  url.searchParams.set("theme_preview", theme);
  return url.toString();
}

async function openScreen(page, origin, screen, theme) {
  const area = screen.visualArea;
  if (screen.captureWidth)
    await page.setViewportSize({ ...page.viewportSize(), width: screen.captureWidth });
  if (area) await page.setViewportSize({ width: area.width, height: area.layoutHeight });
  if (args.now !== "real") await page.clock.setFixedTime(new Date(args.now));
  await page.goto(screenUrl(origin, screen, theme), { waitUntil: "load", timeout: 45_000 });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(waitForQuietDom, { quiet: 600, timeout: 12_000 });
  for (const step of screen.steps || []) {
    if (step.waitHidden)
      await page.locator(step.waitHidden).first().waitFor({ state: "hidden", timeout: 12_000 });
    if (step.scrollTo) await page.locator(step.scrollTo).first().scrollIntoViewIfNeeded();
    if (step.reveal) {
      const content = page.locator(step.reveal.content).filter({ visible: true }).first();
      if (!(await content.count())) await page.locator(step.reveal.trigger).click();
      await content.scrollIntoViewIfNeeded();
    }
    if (step.compose) {
      const { editor, height, lines } = step.compose;
      await page.locator(editor).click();
      if (area) {
        // Model WebViews that resize only the visual viewport. Keep layout and
        // editor rendering native and crop the shot to the area above the IME.
        await page.evaluate(({ height, top, safeTop }) => {
          const viewport = window.visualViewport;
          Object.defineProperties(viewport, {
            height: { configurable: true, value: height },
            offsetTop: { configurable: true, value: top },
          });
          document.documentElement.style.setProperty("--content-safe-area-top", safeTop + "px");
          viewport.dispatchEvent(new Event("resize"));
          viewport.dispatchEvent(new Event("scroll"));
        }, area);
      } else if (height) {
        await page.setViewportSize({ width: page.viewportSize().width, height });
      }
      for (const [index, line] of lines.entries()) {
        if (index) await page.keyboard.press("Shift+Enter");
        await page.keyboard.insertText(line);
      }
    }
    if (step.wait) await page.waitForTimeout(step.wait);
    if (step.press) await page.keyboard.press(step.press);
    if (step.click) {
      const target = page
        .locator(step.click)
        .filter({ visible: true })
        .nth(step.nth || 0);
      await target.scrollIntoViewIfNeeded({ timeout: 8_000 });
      await target.click({ timeout: 8_000 });
    }
    await page.evaluate(waitForQuietDom, { quiet: 500, timeout: 8_000 });
  }
}

async function discoverAdminSections(browser, origin) {
  const context = await newContext(browser, "desktop", "dark");
  const page = await context.newPage();
  try {
    await openScreen(page, origin, { url: "/admin/stats" }, "dark");
    const ids = await page.$$eval("[data-admin-section]", (items) =>
      items.map((item) => item.getAttribute("data-admin-section"))
    );
    return ids.length ? [...new Set(ids)] : demoAdminRoutes;
  } catch (error) {
    console.warn(`admin discovery failed, using demo route list: ${error.message}`);
    return demoAdminRoutes;
  } finally {
    await context.close();
  }
}

const slug = (value) =>
  String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "item";

async function expandVariants(browser, origin, screens) {
  const expanded = [];
  const context = await newContext(browser, "desktop", "dark");
  const page = await context.newPage();
  for (const screen of screens) {
    expanded.push(screen);
    if (!screen.discover || args["no-discover"]) continue;
    try {
      await openScreen(page, origin, screen, "dark");
      const found = await page.evaluate(discoverVariants, {
        kind: screen.discover,
        within: screen.discoverWithin || null,
      });
      const ids = new Set(expanded.map((item) => item.id));
      for (const variant of found) {
        let id = `${screen.id}.${screen.discover === "tabs" ? "tab" : "group"}-${slug(variant.key)}`;
        if (ids.has(id)) id += `-${variant.nth}`;
        ids.add(id);
        expanded.push({
          ...screen,
          id,
          label: variant.label,
          discover: undefined,
          discoverWithin: undefined,
          steps: [...(screen.steps || []), { click: variant.selector, nth: variant.nth }],
        });
      }
    } catch (error) {
      console.warn(`discovery failed for ${screen.id}: ${error.message.split("\n")[0]}`);
    }
  }
  await context.close();
  return expanded;
}

async function createEncoder(browser) {
  const page = await browser.newPage();
  return async (png, quality) => {
    const base64 = await page.evaluate(
      async ({ source, q }) => {
        const image = new Image();
        image.src = "data:image/png;base64," + source;
        await image.decode();
        const canvas = new OffscreenCanvas(image.naturalWidth, image.naturalHeight);
        canvas.getContext("2d").drawImage(image, 0, 0);
        const blob = await canvas.convertToBlob({ type: "image/webp", quality: q });
        const bytes = new Uint8Array(await blob.arrayBuffer());
        let binary = "";
        for (let index = 0; index < bytes.length; index += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
        }
        return btoa(binary);
      },
      { source: png.toString("base64"), q: quality / 100 }
    );
    return Buffer.from(base64, "base64");
  };
}

async function capture(browser, origin, job, encode) {
  const viewport = VIEWPORTS[job.viewport];
  const context = await newContext(browser, job.viewport, job.theme);
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error" && !/favicon|telegram\.org/i.test(message.text())) {
      errors.push(message.text());
    }
  });
  const result = { ...job, steps: undefined, errors, findings: [] };
  try {
    await openScreen(page, origin, job, job.theme);
    let truncated = false;
    if (job.fullPage !== false) {
      let overflow = await page.evaluate(measureOverflow);
      for (let pass = 0; pass < 3 && overflow > 0; pass++) {
        const current = page.viewportSize();
        const height = Math.min(MAX_HEIGHT, current.height + overflow);
        if (height === current.height) break;
        await page.setViewportSize({ width: current.width, height });
        await page.evaluate(waitForQuietDom, { quiet: 400, timeout: 6_000 });
        const next = await page.evaluate(measureOverflow);
        // A dialog with a capped height keeps scrolling inside whatever the
        // viewport is: growing only moves it down a taller blank page.
        if (next >= overflow) {
          await page.setViewportSize(current);
          await page.evaluate(waitForQuietDom, { quiet: 400, timeout: 6_000 });
          break;
        }
        truncated = height === MAX_HEIGHT;
        overflow = next;
      }
    }
    if (!args["no-audit"]) {
      result.findings = await page.evaluate(auditLayout, { mobile: viewport.touch });
    }
    // Long full-page captures also contain images outside the original viewport.
    await page.evaluate(async () => {
      await Promise.all(
        Array.from(document.images, async (image) => {
          image.loading = "eager";
          await image.decode().catch(() => {});
        })
      );
      await document.fonts.ready;
    });
    const area = job.visualArea;
    const clip = area
      ? {
          x: 0,
          y: (await page.evaluate(() => window.scrollY)) + area.top,
          width: area.width,
          height: area.height,
        }
      : undefined;
    const png = await page.screenshot({ type: "png", animations: "disabled", clip });
    const size = clip || page.viewportSize();
    const ext = args.format;
    const file = `${job.viewport}-${job.theme}/${job.id}.${ext}`;
    const bytes = ext === "webp" ? await encode(png, Number(args.quality)) : png;
    await mkdir(path.dirname(path.join(outDir, file)), { recursive: true });
    await writeFile(path.join(outDir, file), bytes);
    Object.assign(result, {
      file,
      width: size.width,
      height: size.height,
      truncated,
      hash: createHash("sha1").update(png).digest("hex"),
    });
  } catch (error) {
    errors.push("capture: " + String(error.message).split("\n")[0]);
  } finally {
    await context.close();
  }
  return result;
}

async function readManifest(dir) {
  try {
    return JSON.parse(await readFile(path.join(dir, "manifest.json"), "utf8"));
  } catch {
    return null;
  }
}

async function loadBaseline() {
  if (!args.baseline) return null;
  const dir = path.resolve(callerDir, args.baseline);
  const manifest = await readManifest(dir);
  if (!manifest) throw new Error(`no manifest.json in baseline ${dir}`);
  return {
    href: path.relative(outDir, dir).split(path.sep).join("/") || ".",
    localPort: manifest.localPort,
    shots: manifest.shots,
  };
}

// Read the baseline first: a wrong path should fail before a long capture, not after it.
const baseline = await loadBaseline();
if (args.build) await run("npm", ["run", "build:demo"], path.join(repoRoot, "docs-site"));
const server = args.base
  ? null
  : await serveDemo(publicRoot, Number(args.port ?? baseline?.localPort ?? 0));
const origin = (args.base || server.origin).replace(/\/$/, "");
const browser = await chromium.launch();
try {
  const sections = await discoverAdminSections(browser, origin);
  const planned = staticScreens(sections).filter(
    (screen) => !onlyPattern || onlyPattern.test(screen.id) || screen.discover
  );
  const screens = (await expandVariants(browser, origin, planned)).filter(
    (screen) => !onlyPattern || onlyPattern.test(screen.id)
  );
  const jobs = [];
  for (const screen of screens) {
    for (const viewport of viewports) {
      if (screen.viewports && !screen.viewports.includes(viewport)) continue;
      for (const theme of themes) jobs.push({ ...screen, viewport, theme });
    }
  }
  if (args.list) {
    for (const job of jobs) console.log(`${job.viewport}-${job.theme}\t${job.id}\t${job.url}`);
    console.log(`${screens.length} screens, ${jobs.length} shots`);
  } else {
    await mkdir(outDir, { recursive: true });
    const encode = await createEncoder(browser);
    const results = [];
    let next = 0;
    const worker = async () => {
      while (next < jobs.length) {
        const job = jobs[next++];
        const shot = await capture(browser, origin, job, encode);
        results.push(shot);
        const flags = [
          shot.errors.length ? `${shot.errors.length} errors` : "",
          shot.findings.length ? `${shot.findings.length} findings` : "",
          shot.truncated ? "truncated" : "",
        ].filter(Boolean);
        console.log(
          `[${results.length}/${jobs.length}] ${job.viewport}-${job.theme} ${job.id}` +
            (flags.length ? `  (${flags.join(", ")})` : "")
        );
      }
    };
    await Promise.all(
      Array.from({ length: Math.max(1, Number(args.concurrency) || 1) }, () => worker())
    );
    const order = new Map(
      jobs.map((job, index) => [`${job.viewport}-${job.theme}/${job.id}`, index])
    );
    results.sort(
      (a, b) =>
        order.get(`${a.viewport}-${a.theme}/${a.id}`) -
        order.get(`${b.viewport}-${b.theme}/${b.id}`)
    );
    // A filtered run into an existing output refreshes those shots in place.
    const previous = onlyPattern ? await readManifest(outDir) : null;
    const shotKey = (shot) => `${shot.viewport}-${shot.theme}/${shot.id}`;
    const fresh = new Map(results.map((shot) => [shotKey(shot), shot]));
    const merged = previous
      ? [
          ...previous.shots.map((shot) => fresh.get(shotKey(shot)) || shot),
          ...results.filter(
            (shot) => !previous.shots.some((old) => shotKey(old) === shotKey(shot))
          ),
        ]
      : results;
    const manifest = {
      generatedAt: new Date().toISOString(),
      clock: args.now,
      localPort: server ? Number(new URL(origin).port) : undefined,
      viewports:
        previous?.viewports || Object.fromEntries(viewports.map((name) => [name, VIEWPORTS[name]])),
      themes: previous?.themes || themes,
      shots: merged,
    };
    await writeFile(path.join(outDir, "manifest.json"), JSON.stringify(manifest, null, 1) + "\n");
    await writeFile(
      path.join(outDir, "index.html"),
      renderGallery({
        title: `UI screens — ${manifest.generatedAt.slice(0, 16)}`,
        shots: merged,
        baseline,
      })
    );
    const failed = results.filter((shot) => !shot.file);
    const changed = baseline
      ? results.filter((shot) => {
          const before = baseline.shots.find(
            (item) =>
              item.id === shot.id && item.viewport === shot.viewport && item.theme === shot.theme
          );
          return before && before.hash !== shot.hash;
        }).length
      : null;
    console.log(
      `\n${results.length - failed.length}/${results.length} shots saved to ${outDir}` +
        (changed === null ? "" : `, ${changed} non-identical captures vs baseline`) +
        `\nGallery: ${path.join(outDir, "index.html")}`
    );
    if (failed.length) {
      console.log(
        "Failed:\n" +
          failed
            .map((shot) => `  ${shot.viewport}-${shot.theme} ${shot.id}: ${shot.errors.at(-1)}`)
            .join("\n")
      );
      process.exitCode = 1;
    }
  }
} finally {
  await browser.close();
  await server?.close();
}
