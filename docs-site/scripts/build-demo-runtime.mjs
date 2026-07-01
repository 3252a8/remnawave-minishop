import { spawn } from "node:child_process";
import {
  access,
  copyFile,
  mkdir,
  readdir,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const siteRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const repoRoot = path.resolve(siteRoot, "..");
const frontendRoot = path.join(repoRoot, "frontend");
const runtimeDir = path.join(siteRoot, "public", "demo", "runtime");
const templatesDir = path.join(
  repoRoot,
  "backend",
  "bot",
  "app",
  "web",
  "templates",
);
const themesDir = path.join(repoRoot, "backend", "bot", "app", "web", "themes");
const localesDir = path.join(repoRoot, "locales");
const runtimeBase = "/demo/runtime";
const installGuidesConfigUrl =
  "https://raw.githubusercontent.com/legiz-ru/my-remnawave/main/sub-page/subpage-config/multiapp.json";
const installGuidesConfigRetries = 3;
const isWindows = process.platform === "win32";
const npmExecPath = process.env.npm_execpath || "";

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: repoRoot,
      stdio: "inherit",
      shell: false,
      ...options,
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) {
        resolve();
        return;
      }
      reject(
        new Error(`${command} ${args.join(" ")} exited with code ${code}`),
      );
    });
  });
}

function runNpm(args) {
  if (npmExecPath) {
    return run(process.execPath, [npmExecPath, ...args]);
  }
  return run(isWindows ? "npm.cmd" : "npm", args, { shell: isWindows });
}

async function pathExists(targetPath) {
  try {
    await access(targetPath);
    return true;
  } catch (_error) {
    return false;
  }
}

async function ensureFrontendDependencies() {
  const viteBin = isWindows
    ? path.join(frontendRoot, "node_modules", ".bin", "vite.cmd")
    : path.join(frontendRoot, "node_modules", ".bin", "vite");
  if (await pathExists(viteBin)) return;
  await runNpm(["--prefix", frontendRoot, "ci"]);
}

async function copyDirectory(sourceDir, targetDir, transform = null) {
  await mkdir(targetDir, { recursive: true });
  const entries = await readdir(sourceDir, { withFileTypes: true });
  for (const entry of entries) {
    const sourcePath = path.join(sourceDir, entry.name);
    const targetPath = path.join(targetDir, entry.name);
    if (entry.isDirectory()) {
      await copyDirectory(sourcePath, targetPath, transform);
      continue;
    }
    if (!entry.isFile()) continue;
    if (transform) {
      const handled = await transform(sourcePath, targetPath);
      if (handled) continue;
    }
    await mkdir(path.dirname(targetPath), { recursive: true });
    await copyFile(sourcePath, targetPath);
  }
}

async function copyThemeFile(sourcePath, targetPath) {
  if (path.extname(sourcePath).toLowerCase() !== ".css") return false;
  const css = await readFile(sourcePath, "utf8");
  const rewritten = css.replace(
    /\/webapp-theme-assets\//g,
    `${runtimeBase}/themes/`,
  );
  await mkdir(path.dirname(targetPath), { recursive: true });
  await writeFile(targetPath, rewritten, "utf8");
  return true;
}

async function copyRuntimeAsset(name) {
  await copyFile(path.join(templatesDir, name), path.join(runtimeDir, name));
}

function isAdminChunkName(name) {
  return (
    /^subscription_webapp_admin\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.js$/.test(
      name,
    ) && !name.startsWith("subscription_webapp_admin.min.")
  );
}

async function copyAdminChunks() {
  const entries = await readdir(templatesDir);
  const chunkNames = entries.filter(isAdminChunkName).sort();
  await Promise.all(chunkNames.map((name) => copyRuntimeAsset(name)));
  return chunkNames;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jsonScriptPayload(value) {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

async function demoI18nPayload() {
  const [ru, en] = await Promise.all([
    readFile(path.join(localesDir, "ru.json"), "utf8"),
    readFile(path.join(localesDir, "en.json"), "utf8"),
  ]);
  return jsonScriptPayload({ ru: JSON.parse(ru), en: JSON.parse(en) });
}

async function installGuidesConfigPayload() {
  let lastError;

  for (let attempt = 1; attempt <= installGuidesConfigRetries; attempt += 1) {
    try {
      const response = await fetch(installGuidesConfigUrl, {
        headers: { accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(
          `Unable to download demo install guides config (${response.status} ${response.statusText})`,
        );
      }
      const config = await response.json();
      return `${JSON.stringify(config, null, 2)}\n`;
    } catch (error) {
      lastError = error;
      if (attempt === installGuidesConfigRetries) break;
      await wait(500 * attempt);
    }
  }

  throw lastError;
}

async function appHtml() {
  const i18n = await demoI18nPayload();
  return `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover"
    />
    <meta name="robots" content="noindex, nofollow" />
    <meta name="theme-color" content="#03070b" />
    <title>remnawave-minishop demo</title>
    <link
      id="app-favicon"
      rel="icon"
      href="${runtimeBase}/default-brand/favicons/19b2a242e5b7bc2d/icon-180.png"
      sizes="180x180"
    />
    <link rel="stylesheet" href="${runtimeBase}/subscription_webapp_docs_demo.css" />
  </head>
  <body>
    <main id="app">
      <div class="app-boot-fallback" role="status" aria-label="Loading demo"></div>
    </main>
    <script id="i18n" type="application/json">${i18n}</script>
    <script src="${runtimeBase}/subscription_webapp_docs_demo.js" defer></script>
  </body>
</html>
`;
}

await ensureFrontendDependencies();
await runNpm(["--prefix", frontendRoot, "run", "build:docs-demo"]);

await rm(runtimeDir, { recursive: true, force: true });
await mkdir(runtimeDir, { recursive: true });
await mkdir(path.join(runtimeDir, "app"), { recursive: true });

const html = await appHtml();

await Promise.all([
  copyRuntimeAsset("subscription_webapp_docs_demo.js"),
  copyRuntimeAsset("subscription_webapp_docs_demo.css"),
  copyRuntimeAsset("subscription_webapp_admin.js"),
  copyRuntimeAsset("subscription_webapp_admin.css"),
  copyAdminChunks(),
  copyDirectory(
    path.join(templatesDir, "default-brand"),
    path.join(runtimeDir, "default-brand"),
  ),
  copyDirectory(themesDir, path.join(runtimeDir, "themes"), copyThemeFile),
  writeFile(path.join(runtimeDir, "app", "index.html"), html, "utf8"),
  installGuidesConfigPayload().then((payload) =>
    writeFile(
      path.join(runtimeDir, "subscription-guides-config.json"),
      payload,
      "utf8",
    ),
  ),
]);

console.log(
  `Built static docs demo runtime at ${path.relative(repoRoot, runtimeDir)}`,
);
