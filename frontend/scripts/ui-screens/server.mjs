// Local static server for the built docs-demo runtime.
//
// Mirrors e2e/serve-demo.mjs: files from docs-site/public are served as-is,
// extensionless routes fall back to the mock app shell so client-side routes
// such as /demo/runtime/admin/users resolve on direct navigation.

import { createReadStream } from "node:fs";
import { access, stat } from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import sharp from "sharp";

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

async function isFile(candidate) {
  try {
    return (await stat(candidate)).isFile();
  } catch {
    return false;
  }
}

/**
 * Serve `publicRoot` on loopback. Reusing a port preserves visible share URLs.
 * @param {string} publicRoot docs-site/public
 * @param {number} port
 * @returns {Promise<{ origin: string, close: () => Promise<void> }>}
 */
export async function serveDemo(publicRoot, port = 0) {
  const appShell = path.join(publicRoot, "demo", "runtime", "app", "index.html");
  await access(appShell).catch(() => {
    throw new Error(
      `demo app shell not found at ${appShell}; run with --build or ` +
        "`npm --prefix docs-site run build:demo` first"
    );
  });
  const rasters = new Map();
  const send = async (res, filePath) => {
    const ext = path.extname(filePath).toLowerCase();
    // CSS and Playwright cannot pause animated image files. Preserve the actual
    // first frame so an unchanged logo compares equally across captures.
    if ([".webp", ".gif", ".png"].includes(ext)) {
      if (!rasters.has(filePath)) {
        const raster = sharp(filePath);
        rasters.set(
          filePath,
          raster
            .metadata()
            .then((info) => (info.pages > 1 ? raster.png().toBuffer() : null))
            .catch(() => null)
        );
      }
      const firstFrame = await rasters.get(filePath);
      if (firstFrame) {
        res.writeHead(200, { "Content-Type": "image/png", "Cache-Control": "no-store" });
        res.end(firstFrame);
        return;
      }
    }
    res.writeHead(200, {
      "Content-Type":
        CONTENT_TYPES.get(path.extname(filePath).toLowerCase()) || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    createReadStream(filePath).pipe(res);
  };
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url || "/", "http://127.0.0.1");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname.endsWith("/")) pathname += "index.html";
    const target = path.normalize(path.join(publicRoot, pathname));
    if (!target.startsWith(publicRoot)) {
      res.writeHead(400).end();
      return;
    }
    if (await isFile(target)) {
      send(res, target);
      return;
    }
    if (path.extname(url.pathname)) {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end(`not found: ${url.pathname}`);
      return;
    }
    send(res, appShell);
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", resolve);
  });
  const address = server.address();
  const boundPort = address.port;
  return {
    origin: `http://127.0.0.1:${boundPort}`,
    close: () => new Promise((resolve) => server.close(() => resolve())),
  };
}
