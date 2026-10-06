// Source-independent test dependencies. A stopped keeper retains the image,
// without a daemon, database, CPU reservation, or resident test process.
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const imageRepository = "docker.io/3252a8/remnawave-minishop-test-runtime";
const lockPath = resolve(repositoryRoot, "deploy/docker/test-runtime.lock.json");
const inputs = [
  "deploy/docker/Dockerfile",
  "deploy/docker/refresh_pip_vendor.py",
  "backend/requirements.txt",
  "requirements-dev.txt",
];

export function run(command, args, options = {}) {
  return new Promise((resolvePromise, reject) => {
    const { inputPath, ...spawnOptions } = options;
    const child = spawn(command, args, {
      cwd: repositoryRoot,
      stdio: inputPath ? ["pipe", "inherit", "inherit"] : "inherit",
      windowsHide: true,
      ...spawnOptions,
    });
    if (inputPath) {
      const input = createReadStream(inputPath);
      input.once("error", (error) => { child.kill(); reject(error); });
      child.stdin.once("error", (error) => { if (error.code !== "EPIPE") reject(error); });
      child.once("exit", () => input.destroy());
      input.pipe(child.stdin);
    }
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) resolvePromise();
      else {
        const error = new Error(`${command} exited with ${signal ?? code}`);
        error.exitCode = code ?? 1;
        reject(error);
      }
    });
  });
}

function probe(args) {
  return spawnSync("docker", args, {
    cwd: repositoryRoot,
    encoding: "utf8",
    windowsHide: true,
    timeout: 15_000,
  });
}

export async function runtimeIdentity() {
  const info = probe(["info", "--format", "{{.OSType}}/{{.Architecture}}"]);
  if (info.status !== 0 || !info.stdout.startsWith("linux/")) {
    throw new Error("A Linux Docker engine is required for the container test runtime");
  }
  const platform = info.stdout.trim().replace("x86_64", "amd64").replace("aarch64", "arm64");
  const hash = createHash("sha256").update(`qa-deps-v1\n${platform}\n`);
  for (const input of inputs) {
    // Git's CRLF conversion must not create a different environment on Windows.
    hash.update(input).update("\0").update((await readFile(resolve(repositoryRoot, input), "utf8")).replaceAll("\r\n", "\n"));
  }
  const fingerprint = hash.digest("hex");
  return {
    fingerprint,
    platform,
    image: `${imageRepository}:${platform.split("/")[1]}-${fingerprint}`,
    keeper: `minishop-core-test-runtime-${platform.split("/")[1]}-${fingerprint.slice(0, 16)}`,
  };
}

export async function ensureRuntime({ refresh = false,
  preferLocal = process.env.MINISHOP_TEST_RUNTIME_CANDIDATE === "1" } = {}) {
  const identity = await runtimeIdentity();
  let lock;
  try { lock = JSON.parse(await readFile(lockPath, "utf8")); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  const pinned = lock?.fingerprint === identity.fingerprint && lock?.platform === identity.platform;
  if (pinned && !/^docker\.io\/3252a8\/remnawave-minishop-test-runtime@sha256:[a-f0-9]{64}$/.test(lock.image)) {
    throw new Error("The test runtime lock must contain an immutable approved image digest");
  }
  let image = pinned && !refresh && !preferLocal ? lock.image : identity.image;
  if (refresh || probe(["image", "inspect", image]).status !== 0) {
    if (pinned && !refresh && !preferLocal) {
      try { await run("docker", ["pull", image]); }
      catch { console.warn("Pinned test runtime unavailable; building the same dependency recipe locally"); image = identity.image; }
    }
    if (refresh || probe(["image", "inspect", image]).status !== 0) {
      image = identity.image;
      const args = ["buildx", "build", "--load", "--target", "qa-deps", "--platform", identity.platform,
        "--tag", image, "--file", "deploy/docker/Dockerfile"];
      if (refresh) args.push("--pull", "--no-cache-filter", "python-dependencies,qa-deps");
      await run("docker", [...args, "."]);
    }
  }
  const imageId = probe(["image", "inspect", "--format", "{{.Id}}", image]).stdout.trim();
  const kept = probe(["container", "inspect", "--format", "{{.Image}}", identity.keeper]);
  if (kept.status === 0 && kept.stdout.trim() !== imageId) {
    await run("docker", ["rm", identity.keeper]);
  }
  if (probe(["container", "inspect", identity.keeper]).status !== 0) {
    try {
      await run("docker", ["create", "--name", identity.keeper, "--network", "none", "--read-only",
        "--label", "minishop.local.keep=true", "--label", "minishop.test.runtime=core", image, "true"]);
    } catch (error) {
      // Two checkouts can prepare the identical environment concurrently.
      const concurrent = probe(["container", "inspect", "--format", "{{.Image}}", identity.keeper]);
      if (concurrent.status !== 0 || concurrent.stdout.trim() !== imageId) throw error;
    }
  }
  console.log(`Test dependencies: ${image} (retained by an unstarted container)`);
  return { ...identity, image };
}

async function main() {
  const command = process.argv[2] ?? "prepare";
  if (command === "identity") { console.log(JSON.stringify(await runtimeIdentity())); return; }
  if (command === "gc") {
    const result = probe(["ps", "-aq", "--filter", "label=minishop.test.runtime=core", "--filter", "status=created"]);
    if (result.status !== 0) throw new Error("Cannot enumerate test runtime keepers");
    const current = await runtimeIdentity();
    // Explicit GC only touches our unstarted keepers, never running test containers.
    for (const id of result.stdout.trim().split(/\s+/).filter(Boolean)) {
      const name = probe(["inspect", "--format", "{{.Name}}", id]).stdout.trim().replace(/^\//, "");
      if (/^minishop-core-test-runtime-[a-z0-9]+-[a-f0-9]{16}$/.test(name) && name !== current.keeper) {
        await run("docker", ["rm", id]);
      }
    }
    console.log("Old test runtime keepers released; unused layers can now be pruned");
    return;
  }
  if (!["prepare", "refresh", "publish"].includes(command)) throw new Error(`Unknown command: ${command}`);
  const runtime = await ensureRuntime({ refresh: command === "refresh", preferLocal:
    command === "publish" || process.env.MINISHOP_TEST_RUNTIME_CANDIDATE === "1" });
  const output = process.argv.indexOf("--output");
  if (output !== -1) {
    if (!process.argv[output + 1]) throw new Error("--output requires a metadata path");
    await writeFile(resolve(process.argv[output + 1]), `${JSON.stringify(runtime, null, 2)}\n`);
  }
  if (command === "publish") {
    // Publication is explicit. Only the dependency stage is uploaded, never the source snapshot.
    const imageId = probe(["image", "inspect", "--format", "{{.Id}}", runtime.image]).stdout.trim();
    if (!/^sha256:[a-f0-9]{64}$/.test(imageId)) throw new Error("Cannot identify candidate image");
    // Refreshing ranges can change layers with the same recipe fingerprint.
    // A unique publication tag also retains older accepted digests in the registry.
    const tag = `${imageRepository}:${runtime.platform.split("/")[1]}-${runtime.fingerprint.slice(0, 32)}-${imageId.slice(7)}`;
    await run("docker", ["tag", runtime.image, tag]);
    await run("docker", ["push", tag]);
    const digests = JSON.parse(probe(["image", "inspect", "--format", "{{json .RepoDigests}}", tag]).stdout);
    const digest = digests.find((item) => item.replace(/^docker\.io\//, "").startsWith("3252a8/remnawave-minishop-test-runtime@sha256:"));
    if (!digest) throw new Error("Registry did not return the test runtime digest");
    await writeFile(lockPath, `${JSON.stringify({ schema: 1, fingerprint: runtime.fingerprint, platform: runtime.platform,
      image: `docker.io/${digest.replace(/^docker\.io\//, "")}`, tag,
      built_at: new Date().toISOString() }, null, 2)}\n`);
    console.log(`Runtime lock written: ${lockPath}`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(error.message); process.exitCode = error.exitCode ?? 1; });
}
