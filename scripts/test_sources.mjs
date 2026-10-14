import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { repositoryRoot, run } from "./test_runtime.mjs";

export async function createSourceSnapshot(directory) {
  const sources = spawnSync("git", ["ls-files", "--cached", "--others", "--exclude-standard", "-z"], {
    cwd: repositoryRoot, encoding: "utf8", windowsHide: true,
  });
  if (sources.status !== 0) throw new Error("Could not list current test sources");
  const paths = [...new Set(sources.stdout.split("\0"))].filter((file) =>
    file && !file.startsWith("graphify-out/") && existsSync(join(repositoryRoot, file)) &&
    !file.split("/").some((part) => part.startsWith(".env") && !part.endsWith(".example")));
  const manifest = join(directory, "files.txt");
  const archive = join(directory, "sources.tar");
  await writeFile(manifest, `${paths.join("\0")}\0`);
  await run("tar", ["-cf", archive, "--null", "-T", manifest]);
  return { manifest, archive };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createSourceSnapshot(dirname(resolve(process.argv[2]))).catch((error) => {
    console.error(error.message); process.exitCode = 1;
  });
}
