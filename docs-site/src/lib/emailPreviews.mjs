import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const repoRootCandidates = [
  resolve(process.cwd(), ".."),
  resolve(process.cwd()),
];
const repoRoot =
  repoRootCandidates.find(
    (candidate) =>
      existsSync(resolve(candidate, "backend")) &&
      existsSync(resolve(candidate, "docs-site")),
  ) || repoRootCandidates[0];
const generatorPath = resolve(
  repoRoot,
  "docs-site",
  "scripts",
  "generate-email-previews.py",
);

const pythonCommands = [
  process.env.PYTHON,
  process.platform === "win32" ? "python" : "python3",
  "python",
].filter(Boolean);

let lastError = "";
let generated = null;
for (const command of pythonCommands) {
  const result = spawnSync(command, [generatorPath], {
    cwd: repoRoot,
    encoding: "utf8",
    maxBuffer: 20 * 1024 * 1024,
    env: {
      ...process.env,
      PYTHONIOENCODING: "utf-8",
    },
  });
  if (result.status === 0 && result.stdout) {
    generated = result.stdout;
    break;
  }
  lastError = [result.error?.message, result.stderr, result.stdout]
    .filter(Boolean)
    .join("\n")
    .trim();
}

if (!generated) {
  throw new Error(
    `Failed to generate email previews from backend templates.\n${lastError}`,
  );
}

export const emailPreviews = JSON.parse(generated);
