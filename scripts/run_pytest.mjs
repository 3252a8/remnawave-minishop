import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdtemp, rmdir, unlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const windowsPython = join(repositoryRoot, ".venv", "Scripts", "python.exe");
const localWindows =
  process.platform === "win32" &&
  !process.env.GITHUB_ACTIONS &&
  !process.env.GITLAB_CI &&
  (!process.env.CI || process.env.MINISHOP_LOCAL_TEST_RUNTIME === "container");
const pytestArguments = ["-q", ...process.argv.slice(2)];
const testImage = "3252a8/remnawave-minishop-tests:local";

function run(command, arguments_) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, arguments_, {
      cwd: repositoryRoot,
      stdio: "inherit",
      windowsHide: true,
    });
    child.once("error", rejectPromise);
    child.once("exit", (code) => {
      if (code === 0) {
        resolvePromise();
      } else {
        const error = new Error(`${command} exited with code ${code}`);
        error.exitCode = code ?? 1;
        rejectPromise(error);
      }
    });
  });
}

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
  if (!endpoint?.startsWith("npipe:")) return false;
  const probe = spawnSync("docker", ["info", "--format", "{{.OSType}}"], {
    encoding: "utf8",
    timeout: 5000,
    windowsHide: true,
  });
  return probe.status === 0 && probe.stdout.trim() === "linux";
}

async function runInLinux() {
  const sources = spawnSync(
    "git",
    ["ls-files", "--cached", "--others", "--exclude-standard", "-z"],
    { cwd: repositoryRoot, encoding: "utf8", windowsHide: true },
  );
  if (sources.status !== 0) throw new Error("Could not list test sources");
  const paths = [...new Set(sources.stdout.split("\0"))].filter(
    (file) =>
      file &&
      !file
        .split("/")
        .some((part) => part.startsWith(".env") && !part.endsWith(".example")),
  );
  const temporaryRoot = await mkdtemp(join(tmpdir(), "minishop-local-tests-"));
  const manifest = join(temporaryRoot, "files.txt");
  const archive = join(temporaryRoot, "sources.tar");
  try {
    await writeFile(manifest, `${paths.join("\0")}\0`);
    await run("tar", ["-cf", archive, "--null", "-T", manifest]);
    await run("docker", [
      "build",
      "--target",
      "qa",
      "--tag",
      testImage,
      "--file",
      "deploy/docker/Dockerfile",
      ".",
    ]);
    console.log(
      "Running local Windows tests from a source snapshot on the Linux filesystem",
    );
    await run("docker", [
      "run",
      "--rm",
      "--mount",
      `type=bind,source=${archive},target=/tmp/minishop-test-sources.tar,readonly`,
      "--env",
      "PYTHONPATH=/workspace/backend:/workspace",
      testImage,
      "bash",
      "-c",
      'tar -xf /tmp/minishop-test-sources.tar -C /workspace && exec "$@"',
      "--",
      "python",
      "-m",
      "pytest",
      ...pytestArguments,
    ]);
  } finally {
    await Promise.allSettled([unlink(manifest), unlink(archive)]);
    await rmdir(temporaryRoot);
  }
}

try {
  if (
    localWindows &&
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
