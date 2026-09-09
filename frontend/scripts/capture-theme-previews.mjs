/* global document, window, FileReader */
import { chromium } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(fileURLToPath(new URL("../..", import.meta.url)));
const themeRoot = path.join(root, "backend/bot/app/web/themes");
const base = process.env.THEME_PREVIEW_BASE_URL || "http://127.0.0.1:8197";
const browser = await chromium.launch({ headless: true });
try {
  for (const key of ["dark", "ascii", "windows95"]) {
    const page = await browser.newPage({
      viewport: { width: 1280, height: 800 },
      deviceScaleFactor: 1,
    });
    await page.goto(base + "/demo/runtime/app/?theme_preview=" + key, { waitUntil: "networkidle" });
    await page.waitForFunction(
      (theme) => document.documentElement.classList.contains("theme-key-" + theme),
      key
    );
    await page.waitForFunction(() =>
      [...document.querySelectorAll('link[rel="stylesheet"]')].every((link) => link.sheet)
    );
    await page.evaluate(() => document.fonts.ready);
    await page.locator(".app-shell").waitFor();
    await page.screenshot({
      path: path.join(themeRoot, key, "preview.png"),
      animations: "disabled",
    });
    const result = spawnSync(
      "python",
      [
        "-c",
        "from PIL import Image; from pathlib import Path; import sys; p=Path(sys.argv[1]); Image.open(p).save(p.with_suffix('.webp'),quality=85,method=6); p.unlink()",
        path.join(themeRoot, key, "preview.png"),
      ],
      { encoding: "utf8" }
    );
    if (result.status) throw new Error(result.stderr);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(themeRoot, key, "preview-mobile.png"),
      animations: "disabled",
    });
    const mobile = spawnSync(
      "python",
      [
        "-c",
        "from PIL import Image; from pathlib import Path; import sys; p=Path(sys.argv[1]); Image.open(p).save(p.with_suffix('.webp'),quality=85,method=6); p.unlink()",
        path.join(themeRoot, key, "preview-mobile.png"),
      ],
      { encoding: "utf8" }
    );
    if (mobile.status) throw new Error(mobile.stderr);
    await page.setViewportSize({ width: 1280, height: 800 });
    if (key === "dark") {
      const snapshot = await page.evaluate(async () => {
        for (const img of document.querySelectorAll("img")) {
          if (!img.src || new URL(img.src).origin !== window.location.origin) continue;
          const response = await fetch(img.src);
          if (!response.ok) continue;
          const data = await response.blob();
          img.src = await new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.readAsDataURL(data);
          });
        }
        const shell = document.querySelector(".app-shell").cloneNode(true);
        shell
          .querySelectorAll("script,iframe,link,style,audio,video")
          .forEach((node) => node.remove());
        for (const element of [shell, ...shell.querySelectorAll("*")]) {
          for (const attribute of [...element.attributes]) {
            if (
              attribute.name.startsWith("on") ||
              ["href", "srcset", "action", "formaction", "nonce"].includes(attribute.name)
            )
              element.removeAttribute(attribute.name);
          }
          if (element.hasAttribute("src") && !element.getAttribute("src").startsWith("data:"))
            element.removeAttribute("src");
          if (element.classList.contains("app-shell")) element.removeAttribute("style");
          for (const token of [...element.classList]) {
            if (token.startsWith("theme-key-"))
              element.classList.replace(token, "THEME_KEY_PLACEHOLDER");
          }
        }
        const css = [...document.styleSheets]
          .flatMap((sheet) => {
            try {
              return [...sheet.cssRules].map((rule) => rule.cssText);
            } catch {
              return [];
            }
          })
          .filter((rule) => !rule.startsWith("@import"))
          .join("\n");
        return {
          html: shell.outerHTML,
          css: css
            .replace(/@font-face\s*\{[^}]*\}/gi, "")
            .replace(/url\((?!['"]?data:)[^)]*\)/gi, "none"),
        };
      });
      const folder = path.join(themeRoot, "preview");
      await mkdir(folder, { recursive: true });
      await writeFile(path.join(folder, "home.html"), snapshot.html + "\n");
      await writeFile(
        path.join(folder, "home.css"),
        snapshot.css
          .split("\n")
          .map((line) => line.trimEnd())
          .join("\n") + "\n"
      );
    }
    console.log("Captured " + key);
    await page.close();
  }
} finally {
  await browser.close();
}
