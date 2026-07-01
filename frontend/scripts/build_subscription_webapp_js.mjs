#!/usr/bin/env node
import { createHash } from "node:crypto";
import { readFile, readdir, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { brotliCompressSync, constants as zlibConstants, gzipSync } from "node:zlib";

import { transform } from "esbuild";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const DEFAULT_JS_MINIFY_TARGET = "es2020";
const ADMIN_JS_MINIFY_TARGET = "es2022";
const templatesDir = path.join(repoRoot, "backend", "bot", "app", "web", "templates");
const JS_BUILDS = [
  {
    sourcePath: path.join(templatesDir, "subscription_webapp.js"),
    outputPrefix: "subscription_webapp.min",
    stripDevMock: true,
    stripFallbackI18nPayload: true,
  },
  {
    sourcePath: path.join(templatesDir, "subscription_webapp_admin.js"),
    outputPrefix: "subscription_webapp_admin.min",
    minifyTarget: ADMIN_JS_MINIFY_TARGET,
  },
];
const CSS_BUILDS = [
  {
    sourcePath: path.join(templatesDir, "subscription_webapp.css"),
    outputPrefix: "subscription_webapp",
  },
  {
    sourcePath: path.join(templatesDir, "subscription_webapp_admin.css"),
    outputPrefix: "subscription_webapp_admin",
  },
];

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
  const i18nLine =
    "    const I18N = readJsonScript('i18n') || (MOCK && MOCK.i18n) || FALLBACK_I18N;";
  const i18nLineIndex = source.indexOf(i18nLine);
  if (fallbackStart === -1 || i18nLineIndex === -1 || i18nLineIndex < fallbackStart) {
    return source;
  }

  return (
    source.slice(0, fallbackStart) +
    "    const I18N = readJsonScript('i18n') || (MOCK && MOCK.i18n) || {};\n" +
    source.slice(i18nLineIndex + i18nLine.length)
  );
}

async function removeOldHashedAssets(assetDir, pattern, keepNames) {
  const keep = new Set(Array.isArray(keepNames) ? keepNames : [keepNames]);
  const entries = await readdir(assetDir, { withFileTypes: true });
  await Promise.all(
    entries
      .filter((entry) => entry.isFile() && pattern.test(entry.name) && !keep.has(entry.name))
      .map((entry) => unlink(path.join(assetDir, entry.name)))
  );
}

async function writePrecompressedAssets(outputPath, body) {
  const buffer = Buffer.isBuffer(body) ? body : Buffer.from(body, "utf8");
  const gzipBody = gzipSync(buffer, { level: 9 });
  const brotliBody = brotliCompressSync(buffer, {
    params: {
      [zlibConstants.BROTLI_PARAM_QUALITY]: 11,
    },
  });

  await Promise.all([
    writeFile(`${outputPath}.gz`, gzipBody),
    writeFile(`${outputPath}.br`, brotliBody),
  ]);

  return {
    gzip: gzipBody.length,
    brotli: brotliBody.length,
  };
}

async function buildJsAsset({
  sourcePath,
  outputPrefix,
  minifyTarget = DEFAULT_JS_MINIFY_TARGET,
  stripDevMock = false,
  stripFallbackI18nPayload = false,
}) {
  const rawSource = await readFile(sourcePath, "utf8");
  let strippedSource = normalizeLineEndings(rawSource);
  if (stripDevMock) {
    strippedSource = stripMarkedBlock(
      strippedSource,
      "/* WEBAPP_DEV_MOCK_START */",
      "/* WEBAPP_DEV_MOCK_END */"
    );
  }
  if (stripFallbackI18nPayload) {
    strippedSource = stripFallbackI18n(strippedSource);
  }
  const result = await transform(strippedSource, {
    charset: "utf8",
    legalComments: "none",
    loader: "js",
    minify: true,
    target: minifyTarget,
  });

  const code = `${result.code.replace(/[ \t]+$/gm, "").trimEnd()}\n`;
  const hash = createHash("sha256").update(code, "utf8").digest("hex").slice(0, 8);
  const outputPath = path.join(path.dirname(sourcePath), `${outputPrefix}.${hash}.js`);
  const outputName = path.basename(outputPath);
  const escapedPrefix = outputPrefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  await removeOldHashedAssets(
    path.dirname(sourcePath),
    new RegExp(`^${escapedPrefix}\\.[0-9a-f]{8}\\.js(?:\\.(?:br|gz))?$`),
    [outputName, `${outputName}.br`, `${outputName}.gz`]
  );
  await writeFile(outputPath, code, "utf8");
  const compressedJs = await writePrecompressedAssets(outputPath, code);
  console.log(
    `Wrote ${path.relative(repoRoot, outputPath)} (${Buffer.byteLength(code, "utf8")} bytes, gzip ${compressedJs.gzip}, br ${compressedJs.brotli})`
  );
}

async function buildCssAsset({ sourcePath, outputPrefix }) {
  const rawCss = await readFile(sourcePath, "utf8");
  const cssResult = await transform(rawCss, {
    legalComments: "none",
    loader: "css",
    minify: true,
  });
  const css = `${cssResult.code.replace(/[ \t]+$/gm, "").trimEnd()}\n`;
  const cssHash = createHash("sha256").update(css, "utf8").digest("hex").slice(0, 8);
  const cssOutputPath = path.join(path.dirname(sourcePath), `${outputPrefix}.${cssHash}.css`);
  const cssOutputName = path.basename(cssOutputPath);
  const escapedPrefix = outputPrefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  await removeOldHashedAssets(
    path.dirname(sourcePath),
    new RegExp(`^${escapedPrefix}\\.[0-9a-f]{8}\\.css(?:\\.(?:br|gz))?$`),
    [cssOutputName, `${cssOutputName}.br`, `${cssOutputName}.gz`]
  );
  await writeFile(cssOutputPath, css, "utf8");
  const compressedCss = await writePrecompressedAssets(cssOutputPath, css);
  console.log(
    `Wrote ${path.relative(repoRoot, cssOutputPath)} (${Buffer.byteLength(css, "utf8")} bytes, gzip ${compressedCss.gzip}, br ${compressedCss.brotli})`
  );
}

async function main() {
  for (const build of JS_BUILDS) {
    await buildJsAsset(build);
  }
  for (const build of CSS_BUILDS) {
    await buildCssAsset(build);
  }
}

await main();
