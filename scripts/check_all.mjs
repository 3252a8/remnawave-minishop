// Native quality tools live outside the checkout, so git clean cannot erase them.
import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { copyFile, lstat, mkdir, open, readFile, realpath, rm, symlink, unlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { delimiter, join, resolve } from "node:path";
import { repositoryRoot, run } from "./test_runtime.mjs";

const cacheRoot = process.env.MINISHOP_TEST_CACHE_DIR || join(
  process.env.LOCALAPPDATA || process.env.XDG_CACHE_HOME || join(homedir(), ".cache"),
  "minishop", "test-envs",
);
const npm = process.platform === "win32" ? process.execPath : "npm";
const npmPrefix = process.platform === "win32"
  ? [join(process.execPath, "..", "node_modules", "npm", "bin", "npm-cli.js")]
  : [];

async function fingerprint(paths) {
  const hash = createHash("sha256").update(`${process.platform}/${process.arch}/node${process.versions.node.split(".")[0]}/python3.12\n`);
  for (const path of paths) hash.update((await readFile(join(repositoryRoot, path), "utf8")).replaceAll("\r\n", "\n"));
  return hash.digest("hex");
}

async function lease(name) {
  const directory = join(cacheRoot, "leases");
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${name}.lock`);
  const deadline = Date.now() + 3_600_000;
  let announced = false;
  while (true) {
    try {
      const file = await open(path, "wx");
      await file.writeFile(JSON.stringify({ pid: process.pid }));
      await file.close();
      return () => unlink(path);
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      let owner;
      try { owner = JSON.parse(await readFile(path, "utf8")); }
      catch (readError) {
        if (readError.code !== "ENOENT" && !(readError instanceof SyntaxError)) throw readError;
      }
      if (Number.isInteger(owner?.pid) && owner.pid > 0) {
        try { process.kill(owner.pid, 0); }
        catch (probeError) {
          if (probeError.code !== "ESRCH") throw probeError;
          throw new Error(`Interrupted gate left ${path}; after checking that no gate is active, remove that lock and retry`);
        }
      }
      if (Date.now() > deadline) throw new Error(`Timed out waiting for ${path}; check its owner before removing it`);
      if (!announced) { console.log(`Waiting for another local gate: ${name}`); announced = true; }
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 1_000));
    }
  }
}

async function prepare() {
  const key = await fingerprint(["backend/requirements.txt", "requirements-dev.txt"]);
  const environment = join(cacheRoot, "core", key);
  const bin = join(environment, process.platform === "win32" ? "Scripts" : "bin");
  const python = join(bin, process.platform === "win32" ? "python.exe" : "python");
  const ready = join(environment, ".minishop-ready");
  if (!existsSync(ready) || !existsSync(python) || process.env.MINISHOP_TEST_REFRESH === "1") {
    await mkdir(environment, { recursive: true });
    if (!existsSync(python)) await run("uv", ["venv", "--python", "3.12", environment]);
    await run("uv", ["pip", "install", ...(process.env.MINISHOP_TEST_REFRESH === "1" ? ["--upgrade"] : []),
      "--python", python, "-r", "backend/requirements.txt", "-r", "requirements-dev.txt"]);
    await writeFile(ready, key);
  }
  const frontendKey = await fingerprint(["frontend/package.json", "frontend/package-lock.json"]);
  const nodeEnvironment = join(cacheRoot, "core-node", frontendKey);
  const modules = join(nodeEnvironment, "node_modules");
  const stamp = join(modules, ".minishop-lock");
  let installed;
  try { installed = await readFile(stamp, "utf8"); } catch { /* First installation. */ }
  if (installed !== frontendKey || !existsSync(join(modules, ".bin/vite"))) {
    await mkdir(nodeEnvironment, { recursive: true });
    for (const name of ["package.json", "package-lock.json"]) {
      await copyFile(join(repositoryRoot, "frontend", name), join(nodeEnvironment, name));
    }
    await run(npm, [...npmPrefix, "--prefix", nodeEnvironment, "ci", "--no-audit", "--no-fund"]);
    await writeFile(stamp, frontendKey);
  }
  const link = resolve(repositoryRoot, "frontend", "node_modules");
  let info;
  try { info = await lstat(link); } catch { /* Checkout after a clean. */ }
  // Only the disposable dependency directory in this exact checkout is replaced.
  if (link !== join(repositoryRoot, "frontend", "node_modules")) throw new Error("Invalid dependency link");
  const linked = info && (await realpath(link)) === resolve(modules);
  if (!linked) {
    if (info) await rm(link, { recursive: !info.isSymbolicLink(), force: true });
    await symlink(modules, link, process.platform === "win32" ? "junction" : "dir");
  }
  console.log(`Native quality environment retained outside checkout: ${environment}`);
  return {
    ...process.env,
    PATH: `${bin}${delimiter}${process.env.PATH}`,
    NODE_COMPILE_CACHE: join(cacheRoot, "node-compile", process.versions.node),
  };
}

try {
  const checkoutKey = createHash("sha256").update(repositoryRoot).digest("hex").slice(0, 16);
  const releaseCheckout = await lease(`core-checkout-${checkoutKey}`);
  try {
    const releaseBootstrap = await lease("core-bootstrap");
    let env;
    try { env = await prepare(); } finally { await releaseBootstrap(); }
    if (process.argv[2] !== "--prepare") {
      await run(npm, [...npmPrefix, "run", process.argv[2] === "--all" ? "qa:all" : "check"], { env });
    }
  } finally {
    await releaseCheckout();
  }
} catch (error) { console.error(error.message); process.exitCode = error.exitCode ?? 1; }
