#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, readdir, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { transform } from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const sourcePath = path.join(
  repoRoot,
  "bot",
  "app",
  "web",
  "templates",
  "subscription_webapp.js",
);

function normalizeLineEndings(value) {
  return value.replace(/\r\n/g, "\n");
}

function stripMarkedBlock(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  if (start === -1) {
    return source;
  }
  const end = source.indexOf(endMarker, start);
  if (end === -1) {
    return source.slice(0, start);
  }
  return source.slice(0, start) + source.slice(end + endMarker.length);
}

function stripFallbackI18n(source) {
  const fallbackStart = source.indexOf("    const FALLBACK_I18N = {");
  const i18nLine = "    const I18N = readJsonScript('i18n') || (MOCK && MOCK.i18n) || FALLBACK_I18N;";
  const i18nLineIndex = source.indexOf(i18nLine);
  if (fallbackStart === -1 || i18nLineIndex === -1 || i18nLineIndex < fallbackStart) {
    return source;
  }

  return (
    source.slice(0, fallbackStart)
    + "    const I18N = readJsonScript('i18n') || (MOCK && MOCK.i18n) || {};\n"
    + source.slice(i18nLineIndex + i18nLine.length)
  );
}

async function removeOldMinifiedAssets(assetDir, keepName) {
  const entries = await readdir(assetDir, { withFileTypes: true });
  await Promise.all(
    entries
      .filter(
        (entry) => entry.isFile() && /^subscription_webapp\.min\.[0-9a-f]{8}\.js$/.test(entry.name) && entry.name !== keepName,
      )
      .map((entry) => unlink(path.join(assetDir, entry.name))),
  );
}

async function main() {
  const rawSource = await readFile(sourcePath, "utf8");
  const withoutMocks = stripMarkedBlock(
    normalizeLineEndings(rawSource),
    "/* WEBAPP_DEV_MOCK_START */",
    "/* WEBAPP_DEV_MOCK_END */",
  );
  const strippedSource = stripFallbackI18n(withoutMocks);
  const result = await transform(strippedSource, {
    charset: "utf8",
    legalComments: "none",
    loader: "js",
    minify: true,
    target: "es2018",
  });

  const code = `${result.code.replace(/[ \t]+$/gm, "").trimEnd()}\n`;
  const hash = createHash("sha256").update(code, "utf8").digest("hex").slice(0, 8);
  const outputPath = path.join(
    path.dirname(sourcePath),
    `subscription_webapp.min.${hash}.js`,
  );

  await removeOldMinifiedAssets(path.dirname(sourcePath), path.basename(outputPath));
  await writeFile(outputPath, code, "utf8");
  console.log(`Wrote ${path.relative(repoRoot, outputPath)} (${Buffer.byteLength(code, "utf8")} bytes)`);
}

await main();
