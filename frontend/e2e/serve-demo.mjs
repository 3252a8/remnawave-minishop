// Build (unless skipped) and statically serve the docs-demo runtime for the
// Playwright mock-smoke suite. Zero runtime dependencies — uses only Node
// builtins so the e2e job stays light and cross-platform (Windows + Linux CI).
//
// Behavior:
//   - Unless PLAYWRIGHT_SKIP_DEMO_BUILD=1, rebuilds the demo runtime from the
//     current source (`npm run build:demo` in ../docs-site) so the suite always
//     runs against the latest code, not a stale bundle.
//   - Serves ../docs-site/public on PORT (default 8090) with an SPA fallback to
//     the mock app shell so client-side routes resolve on direct navigation.

import { spawn } from "node:child_process";
import { createReadStream } from "node:fs";
import { access, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)));
const repoRoot = path.resolve(frontendRoot, "..");
const docsSiteRoot = path.join(repoRoot, "docs-site");
const publicRoot = path.join(docsSiteRoot, "public");
const appShell = path.join(publicRoot, "demo", "runtime", "app", "index.html");

const PORT = Number(process.env.PORT || 8090);
const HOST = process.env.HOST || "127.0.0.1";
const SKIP_BUILD = process.env.PLAYWRIGHT_SKIP_DEMO_BUILD === "1";
const isWindows = process.platform === "win32";

const CONTENT_TYPES = new Map([
  [".html", "text/html; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".mjs", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
  [".png", "image/png"],
  [".webp", "image/webp"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".gif", "image/gif"],
  [".ico", "image/x-icon"],
  [".woff", "font/woff"],
  [".woff2", "font/woff2"],
  [".ttf", "font/ttf"],
  [".map", "application/json; charset=utf-8"],
]);

function contentTypeFor(filePath) {
  return CONTENT_TYPES.get(path.extname(filePath).toLowerCase()) || "application/octet-stream";
}

async function isFile(candidate) {
  try {
    const info = await stat(candidate);
    return info.isFile();
  } catch {
    return false;
  }
}

function runDemoBuild() {
  return new Promise((resolve, reject) => {
    const npmCmd = isWindows ? "npm.cmd" : "npm";
    const child = spawn(npmCmd, ["run", "build:demo"], {
      cwd: docsSiteRoot,
      stdio: "inherit",
      shell: isWindows,
    });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`demo build exited with code ${code}`));
    });
  });
}

function resolveRequestPath(urlPath) {
  // Decode + strip query, normalize, and prevent path traversal escapes.
  let pathname = decodeURIComponent(urlPath.split("?")[0]);
  if (pathname.endsWith("/")) pathname += "index.html";
  const resolved = path.normalize(path.join(publicRoot, pathname));
  if (!resolved.startsWith(publicRoot)) return null;
  return resolved;
}

function sendFile(res, filePath, statusCode = 200) {
  res.writeHead(statusCode, {
    "Content-Type": contentTypeFor(filePath),
    "Cache-Control": "no-store",
  });
  createReadStream(filePath).pipe(res);
}

async function startServer() {
  await access(appShell).catch(() => {
    throw new Error(
      `demo app shell not found at ${appShell}; build the demo first (npm run build:demo in docs-site)`
    );
  });

  const server = http.createServer(async (req, res) => {
    const target = resolveRequestPath(req.url || "/");
    if (target && (await isFile(target))) {
      sendFile(res, target);
      return;
    }
    // SPA fallback: the mock app does client-side routing under /demo/runtime/,
    // and those routes carry no file extension. An asset request that misses is
    // a broken build, so it 404s instead of being answered with the app shell —
    // HTML served as a module fails somewhere far away from the actual cause.
    if (target && path.extname(target)) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end(`not found: ${req.url}`);
      return;
    }
    sendFile(res, appShell);
  });

  await new Promise((resolve) => server.listen(PORT, HOST, resolve));
  console.log(`Serving demo runtime at http://${HOST}:${PORT}/demo/runtime/app/`);
}

if (!SKIP_BUILD) {
  await runDemoBuild();
} else {
  console.log("PLAYWRIGHT_SKIP_DEMO_BUILD=1 — serving existing demo runtime build");
}
await startServer();
