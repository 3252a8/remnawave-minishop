import { build } from "../frontend/node_modules/esbuild/lib/main.js";
import { zipSync, strToU8 } from "../frontend/node_modules/fflate/esm/index.mjs";
import { mkdir, readFile, writeFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const check = process.argv.includes("--check");
for (const name of ["tilt"]) {
  const folder = path.join(root, "examples/theme-effects", name);
  const result = await build({
    entryPoints: [path.join(root, "examples/theme-effects-src", name + ".ts")],
    bundle: true, format: "esm", target: "es2022", minify: true, write: false,
  });
  const output = result.outputFiles[0].contents;
  const entry = path.join(folder, "effects/main.js");
  if (check) {
    if (!Buffer.from(output).equals(await readFile(entry))) throw Error("Stale example: " + name);
  } else {
    await mkdir(path.dirname(entry), { recursive: true });
    await writeFile(entry, output);
  }
  const files = {};
  const entries = (await readdir(folder, { recursive: true, withFileTypes: true }))
    .filter(file => file.isFile()).map(file => path.join(file.parentPath, file.name)).sort();
  for (const absolute of entries) {
    const relative = path.relative(folder, absolute).replaceAll("\\", "/");
    const content = await readFile(absolute);
    // Keep the checked-in archive identical on LF and autocrlf checkouts.
    const normalized = /\.(?:js|css|json|md|txt)$/.test(relative) || relative === "LICENSE"
      ? strToU8(content.toString("utf8").replaceAll("\r\n", "\n"))
      : new Uint8Array(content);
    files[name + "/" + relative] = [normalized, { mtime: new Date("2020-01-01T00:00:00Z") }];
  }
  files["minishop-themes.json"] = [strToU8(JSON.stringify({ schema_version: 1, themes: [{ path: name }] })), { mtime: new Date("2020-01-01T00:00:00Z") }];
  const zipped = zipSync(files, { level: 6 });
  const archive = path.join(root, "examples/theme-effects", name + ".zip");
  if (check) {
    if (!Buffer.from(zipped).equals(await readFile(archive))) throw Error("Stale archive: " + name);
  } else await writeFile(archive, zipped);
}
