import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  demoPublicRoutes,
  demoRuntimeRoutes,
} from "../src/lib/demoRoutes.mjs";

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
const runtimeApp = path.join(
  distRoot,
  "demo",
  "runtime",
  "app",
  "index.html",
);

for (const route of demoRoutes) {
  await copyHtml(demoShell, route);
}

for (const route of runtimeRoutes) {
  await copyHtml(runtimeApp, route);
}

console.log(
  `Materialized ${demoRoutes.length} public demo routes and ${runtimeRoutes.length} runtime routes`,
);
