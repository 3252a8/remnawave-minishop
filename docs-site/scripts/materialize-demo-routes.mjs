import { copyFile, mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { demoPublicRoutes, demoRuntimeRoutes } from "../src/lib/demoRoutes.mjs";

const siteRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const distRoot = path.join(siteRoot, "dist");

const demoRoutes = demoPublicRoutes.map((route) => `demo/${route}`);
const runtimeRoutes = demoRuntimeRoutes.map((route) => `demo/runtime/${route}`);

async function copyHtml(source, route) {
  const targetDir = path.join(distRoot, route);
  await mkdir(targetDir, { recursive: true });
  await copyFile(source, path.join(targetDir, "index.html"));
}

const demoShell = path.join(distRoot, "demo", "index.html");
const runtimeApp = path.join(distRoot, "demo", "runtime", "app", "index.html");

for (const route of demoRoutes) {
  await copyHtml(demoShell, route);
}

for (const route of runtimeRoutes) {
  await copyHtml(runtimeApp, route);
}

// Write the deployment proof only after the complete production build succeeds.
if (process.env.CF_PAGES_COMMIT_SHA) {
  const commit = process.env.CF_PAGES_COMMIT_SHA;
  if (!/^[0-9a-f]{40}$/.test(commit) || !process.env.CF_PAGES_BRANCH) {
    throw new Error("Cloudflare build identity is invalid");
  }
  await writeFile(
    path.join(distRoot, "_build.json"),
    `${JSON.stringify({ schema: 1, repository: "3252a8/remnawave-minishop", commit, branch: process.env.CF_PAGES_BRANCH })}\n`,
  );
}

console.log(
  `Materialized ${demoRoutes.length} public demo routes and ${runtimeRoutes.length} runtime routes`,
);
