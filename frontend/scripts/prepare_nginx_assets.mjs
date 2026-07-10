#!/usr/bin/env node
import {
  cp,
  copyFile,
  lstat,
  mkdir,
  readdir,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const templatesDir = path.join(repoRoot, "backend", "bot", "app", "web", "templates");
const DEFAULT_OUT_DIR = path.join(repoRoot, "frontend-nginx-dist");
const outDir = resolveOutDir();

function resolveOutDir() {
  const argIndex = process.argv.indexOf("--out");
  if (argIndex === -1) {
    return DEFAULT_OUT_DIR;
  }
  const rawValue = process.argv[argIndex + 1];
  if (!rawValue) {
    throw new Error("--out requires a directory path");
  }
  return path.resolve(process.cwd(), rawValue);
}

async function pathExists(filePath) {
  try {
    await lstat(filePath);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

async function copyIfExists(sourceName, targetName = sourceName) {
  const sourcePath = path.join(templatesDir, sourceName);
  if (!(await pathExists(sourcePath))) return false;
  await copyFile(sourcePath, path.join(outDir, targetName));
  return true;
}

async function copyDirectoryIfExists(sourceName, targetName = sourceName) {
  const sourcePath = path.join(templatesDir, sourceName);
  if (!(await pathExists(sourcePath))) return false;
  await cp(sourcePath, path.join(outDir, targetName), { recursive: true });
  return true;
}

async function linkOrCopy(targetName, aliasName) {
  const aliasPath = path.join(outDir, aliasName);
  try {
    await symlink(targetName, aliasPath);
  } catch (error) {
    if (!["EPERM", "EINVAL", "ENOSYS"].includes(error?.code)) {
      throw error;
    }
    await copyFile(path.join(outDir, targetName), aliasPath);
  }
}

function latestMatching(entries, pattern, fallbackName) {
  const matches = entries.filter((name) => pattern.test(name)).sort();
  return matches.at(-1) || fallbackName;
}

async function copyRuntimeAsset({ hashedName, stableName }) {
  const copied = await copyIfExists(hashedName);
  if (copied && hashedName !== stableName) {
    await linkOrCopy(hashedName, stableName);
  } else if (!copied) {
    await copyIfExists(stableName);
  }

  const gzipName = `${hashedName}.gz`;
  const gzipCopied = await copyIfExists(gzipName);
  if (gzipCopied && hashedName !== stableName) {
    await linkOrCopy(gzipName, `${stableName}.gz`);
  }

  const brotliName = `${hashedName}.br`;
  const brotliCopied = await copyIfExists(brotliName);
  if (brotliCopied && hashedName !== stableName) {
    await linkOrCopy(brotliName, `${stableName}.br`);
  }
}

function prepareIndexHtml(rawHtml, { cssName, jsName }) {
  const jsPreload = `    <link rel="preload" href="/${jsName}" as="script">`;
  const html = rawHtml
    .replace(/\r\n/g, "\n")
    .replace('href="/subscription_webapp.css"', `href="/${cssName}"`)
    .replace("</head>", `${jsPreload}\n  </head>`);
  const lines = html.split("\n");
  const output = lines
    .map((line) =>
      line.includes("WEBAPP_JS_SCRIPT") ? `    <script src="/${jsName}" defer></script>` : line
    )
    .filter(
      (line) =>
        !line.includes("WEBAPP_I18N_SCRIPT") &&
        !line.includes("WEBAPP_CONFIG_SCRIPT") &&
        !line.includes("WEBAPP_DEV_MOCK_START") &&
        !line.includes("WEBAPP_DEV_MOCK_END") &&
        !line.includes('subscription_webapp.js" defer')
    )
    .join("\n");
  return output.endsWith("\n") ? output : `${output}\n`;
}

function isAdminChunkName(name) {
  return (
    /^subscription_webapp_admin\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.js$/.test(name) &&
    name !== "subscription_webapp_admin.js" &&
    !name.startsWith("subscription_webapp_admin.min.")
  );
}

async function copyAdminChunkAssets(entries) {
  const chunkNames = entries.filter(isAdminChunkName).sort();
  await Promise.all(
    chunkNames.map((chunkName) =>
      copyRuntimeAsset({ hashedName: chunkName, stableName: chunkName })
    )
  );
  return chunkNames;
}

async function main() {
  const entries = await readdir(templatesDir);
  const mainJsName = latestMatching(
    entries,
    /^subscription_webapp\.min\.[0-9a-f]{8}\.js$/,
    "subscription_webapp.js"
  );
  const mainCssName = latestMatching(
    entries,
    /^subscription_webapp\.[0-9a-f]{8}\.css$/,
    "subscription_webapp.css"
  );
  const adminJsName = latestMatching(
    entries,
    /^subscription_webapp_admin\.min\.[0-9a-f]{8}\.js$/,
    "subscription_webapp_admin.js"
  );
  const adminCssName = latestMatching(
    entries,
    /^subscription_webapp_admin\.[0-9a-f]{8}\.css$/,
    "subscription_webapp_admin.css"
  );

  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });

  await Promise.all([
    copyRuntimeAsset({ hashedName: mainJsName, stableName: "subscription_webapp.js" }),
    copyRuntimeAsset({ hashedName: mainCssName, stableName: "subscription_webapp.css" }),
    copyRuntimeAsset({ hashedName: adminJsName, stableName: "subscription_webapp_admin.js" }),
    copyRuntimeAsset({ hashedName: adminCssName, stableName: "subscription_webapp_admin.css" }),
  ]);
  const adminChunkNames = await copyAdminChunkAssets(entries);
  const providerLogoAssetsCopied = await copyDirectoryIfExists("provider-logos");

  const indexTemplate = await readFile(path.join(templatesDir, "subscription_webapp.html"), "utf8");
  await writeFile(
    path.join(outDir, "index.html"),
    prepareIndexHtml(indexTemplate, { cssName: mainCssName, jsName: mainJsName }),
    "utf8"
  );

  console.log(
    `Prepared nginx assets in ${path.relative(repoRoot, outDir)}: ${mainJsName}, ${mainCssName}, ${adminJsName}, ${adminCssName}, ${adminChunkNames.length} admin chunks, ${providerLogoAssetsCopied ? "provider logos" : "no provider logos"}`
  );
}

await main();
