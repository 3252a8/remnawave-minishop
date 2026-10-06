import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rmdir, unlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import process from "node:process";
import { ensureRuntime, run } from "./test_runtime.mjs";
import { createSourceSnapshot } from "./test_sources.mjs";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const windowsPython = join(repositoryRoot, ".venv", "Scripts", "python.exe");
const localWindows =
  process.platform === "win32" &&
  !process.env.GITHUB_ACTIONS &&
  !process.env.GITLAB_CI &&
  (!process.env.CI || process.env.MINISHOP_LOCAL_TEST_RUNTIME === "container");
const pytestArguments = ["-q", ...process.argv.slice(2)];


function linuxDockerAvailable() {
  let endpoint = process.env.DOCKER_HOST;
  if (!endpoint) {
    const context = spawnSync("docker", ["context", "inspect"], {
      encoding: "utf8",
      timeout: 5000,
      windowsHide: true,
    });
    if (context.status !== 0) return false;
    try {
      endpoint = JSON.parse(context.stdout)[0]?.Endpoints?.docker?.Host;
    } catch {
      return false;
    }
  }
  if (process.env.MINISHOP_LOCAL_TEST_RUNTIME !== "container" && !endpoint?.startsWith("npipe:")) return false;
  const probe = spawnSync("docker", ["info", "--format", "{{.OSType}}"], {
    encoding: "utf8",
    timeout: 5000,
    windowsHide: true,
  });
  return probe.status === 0 && probe.stdout.trim() === "linux";
}

async function runInLinux() {
  const temporaryRoot = await mkdtemp(join(tmpdir(), "minishop-local-tests-"));
  const manifest = join(temporaryRoot, "files.txt");
  const archive = join(temporaryRoot, "sources.tar");
  try {
    await createSourceSnapshot(temporaryRoot);
    const { image: testImage } = await ensureRuntime();
    console.log(
      "Running tests from a fresh source snapshot on the Linux filesystem",
    );
    await run("docker", [
      "run",
      "--rm",
      "--interactive",
      "--init",
      "--label", "minishop.test.run=core",
      "--cpus", process.env.MINISHOP_TEST_CPUS || "4",
      "--memory", process.env.MINISHOP_TEST_MEMORY || "4g",
      "--memory-swap", process.env.MINISHOP_TEST_MEMORY || "4g",
      "--env",
      "PYTHONPATH=/workspace/backend:/workspace",
      testImage,
      "bash",
      "-c",
      'tar -xf - -C /workspace && exec "$@"',
      "--",
      "timeout",
      "--signal=TERM",
      "--kill-after=30s",
      process.env.MINISHOP_TEST_TIMEOUT || "2h",
      "python",
      "-m",
      "pytest",
      ...pytestArguments,
    ], { inputPath: archive });
  } finally {
    await Promise.allSettled([unlink(manifest), unlink(archive)]);
    await rmdir(temporaryRoot);
  }
}

try {
  if (
    (localWindows || process.env.MINISHOP_LOCAL_TEST_RUNTIME === "container") &&
    process.env.MINISHOP_LOCAL_TEST_RUNTIME !== "native" &&
    linuxDockerAvailable()
  ) {
    await runInLinux();
  } else if (localWindows && existsSync(windowsPython)) {
    console.log("Running local Windows tests with .venv/Scripts/python.exe");
    await run(windowsPython, ["-m", "pytest", ...pytestArguments]);
  } else {
    await run("pytest", pytestArguments);
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = error.exitCode ?? 1;
}
