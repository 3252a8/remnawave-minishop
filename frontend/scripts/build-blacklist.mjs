import { createHash } from "node:crypto";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = new URL("../../backend/bot/plugins/builtin/blacklist/", import.meta.url);
const output = new URL("dist/", root);
const files = {};
const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");

const result = await build({
  entryPoints: [fileURLToPath(new URL("../plugins/blacklist/index.ts", import.meta.url))],
  outdir: fileURLToPath(new URL("frontend/admin/", output)),
  bundle: true,
  format: "esm",
  target: "es2022",
  minify: true,
  write: false,
});
await mkdir(new URL("frontend/admin/", output), { recursive: true });
for (const artifact of result.outputFiles) {
  const name = "frontend/admin/" + artifact.path.split(/[\\/]/).pop();
  files[name] = sha256(artifact.contents);
  await writeFile(new URL(name, output), artifact.contents);
}

const manifest = JSON.parse(await readFile(new URL("manifest.json", root), "utf8"));
const sources = (await readdir(root)).filter((name) => name.endsWith(".py"));
for (const name of [...sources.sort(), "locales/en.json", "locales/ru.json", "LICENSE"]) {
  // Include Python and translations in the generation identity, even for backend-only updates.
  files[name] = sha256(await readFile(new URL(name, root)));
}
await writeFile(new URL("plugin.json", output), JSON.stringify({ ...manifest, files }) + "\n");
