import { spawn } from "node:child_process";
import { copyFile, mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve, sep } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const projectNames = ["frontend", "docs-site"];

function selectedProjects(arguments_) {
  if (arguments_.length === 0) return projectNames;

  const selected = projectNames.filter((projectName) =>
    arguments_.some((argument) => {
      const pathFromRoot = relative(
        repositoryRoot,
        resolve(repositoryRoot, argument),
      );
      return (
        pathFromRoot === projectName ||
        pathFromRoot.startsWith(`${projectName}${sep}`)
      );
    }),
  );
  return selected.length > 0 ? selected : projectNames;
}

function npmVersionFrom(packageJson, projectName) {
  const match = /^npm@(\d+\.\d+\.\d+)$/.exec(packageJson.packageManager ?? "");
  if (!match) {
    throw new Error(
      `${projectName}/package.json must declare an exact packageManager such as npm@10.9.9`,
    );
  }
  return match[1];
}

function run(command, arguments_, options) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, arguments_, { ...options, stdio: "inherit" });
    child.once("error", rejectPromise);
    child.once("exit", (code, signal) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      const detail = signal ? `signal ${signal}` : `exit code ${code}`;
      rejectPromise(new Error(`${command} failed with ${detail}`));
    });
  });
}

async function checkProject(projectName) {
  const projectRoot = join(repositoryRoot, projectName);
  const packageJsonPath = join(projectRoot, "package.json");
  const lockfilePath = join(projectRoot, "package-lock.json");
  const packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
  const npmVersion = npmVersionFrom(packageJson, projectName);
  const temporaryRoot = await mkdtemp(
    join(tmpdir(), `minishop-${projectName}-lockfile-`),
  );
  const npmArguments = [
    "--yes",
    `npm@${npmVersion}`,
    "ci",
    "--dry-run",
    "--ignore-scripts",
    "--no-audit",
    "--no-fund",
    "--loglevel=error",
    "--silent",
  ];
  const command =
    process.platform === "win32" ? (process.env.ComSpec ?? "cmd.exe") : "npx";
  const arguments_ =
    process.platform === "win32"
      ? ["/d", "/s", "/c", "npx", ...npmArguments]
      : npmArguments;

  try {
    await copyFile(packageJsonPath, join(temporaryRoot, "package.json"));
    await copyFile(lockfilePath, join(temporaryRoot, "package-lock.json"));
    console.log(
      `Checking ${projectName}/package-lock.json with npm ${npmVersion}...`,
    );
    await run(command, arguments_, {
      cwd: temporaryRoot,
      env: { ...process.env, npm_config_update_notifier: "false" },
    });
  } catch (error) {
    console.error(
      `\n${projectName}/package-lock.json is not synchronized with package.json.`,
    );
    console.error(
      `Regenerate it with npm ${npmVersion}: cd ${projectName} && npx --yes npm@${npmVersion} install --package-lock-only --ignore-scripts --no-audit --no-fund`,
    );
    throw error;
  } finally {
    await rm(temporaryRoot, { recursive: true, force: true });
  }
}

for (const projectName of selectedProjects(process.argv.slice(2))) {
  await checkProject(projectName);
}

console.log("npm lockfiles are synchronized.");
