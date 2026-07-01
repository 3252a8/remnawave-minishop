#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const presetsDir = path.join(repoRoot, "deploy", "dev", "remnawave-stands");
const baseEnvPath = path.join(repoRoot, "deploy", "dev", "remnawave-dev.env.example");
const targetEnvPath = path.join(repoRoot, ".env.remnawave-dev");
const presetName = process.argv[2];

function listPresets() {
  return fs
    .readdirSync(presetsDir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function parseEnvFile(filePath) {
  const entries = [];
  for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const match = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(rawLine);
    if (!match) {
      throw new Error(`Invalid env line in ${path.relative(repoRoot, filePath)}: ${rawLine}`);
    }
    entries.push([match[1], match[2]]);
  }
  return entries;
}

function validateLock(lockPath, envMap) {
  const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));
  const expected = new Map([
    ["REMNAWAVE_DEV_VERSION", lock.remnawave_panel],
    ["REMNAWAVE_NODE_VERSION", lock.remnawave_node],
    ["REMNAWAVE_SUBSCRIPTION_PAGE_VERSION", lock.subscription_page],
  ]);

  for (const [key, value] of expected) {
    if (envMap.get(key) !== value) {
      throw new Error(
        `${key}=${envMap.get(key) ?? "<missing>"} does not match ${path.relative(
          repoRoot,
          lockPath,
        )} (${value})`,
      );
    }
  }

  return lock;
}

if (!presetName) {
  console.error("Usage: npm run dev:stand:use -- <version>");
  console.error(`Available presets: ${listPresets().join(", ")}`);
  process.exit(1);
}

const presetDir = path.join(presetsDir, presetName);
const standEnvPath = path.join(presetDir, "stand.env");
const lockPath = path.join(presetDir, "versions.lock.json");

if (!fs.existsSync(standEnvPath) || !fs.existsSync(lockPath)) {
  console.error(`Unknown Remnawave dev stand preset: ${presetName}`);
  console.error(`Available presets: ${listPresets().join(", ")}`);
  process.exit(1);
}

const presetEntries = parseEnvFile(standEnvPath);
const presetMap = new Map(presetEntries);
const lock = validateLock(lockPath, presetMap);
const usedKeys = new Set();

const output = fs
  .readFileSync(baseEnvPath, "utf8")
  .replace(/\r\n/g, "\n")
  .split("\n")
  .map((line) => {
    const match = /^([A-Za-z_][A-Za-z0-9_]*)=/.exec(line);
    if (!match || !presetMap.has(match[1])) {
      return line;
    }
    usedKeys.add(match[1]);
    return `${match[1]}=${presetMap.get(match[1])}`;
  });

while (output.length > 0 && output.at(-1) === "") {
  output.pop();
}

const extraEntries = presetEntries.filter(([key]) => !usedKeys.has(key));
if (extraEntries.length > 0) {
  output.push(
    "",
    `# Applied by scripts/use_dev_stand_preset.mjs from ${path.relative(
      repoRoot,
      standEnvPath,
    )}.`,
  );
  for (const [key, value] of extraEntries) {
    output.push(`${key}=${value}`);
  }
}

fs.writeFileSync(targetEnvPath, `${output.join("\n")}\n`, "utf8");

console.log(`Selected Remnawave dev stand preset ${presetName}`);
console.log(`Panel ${lock.remnawave_panel}, Node ${lock.remnawave_node}, Subscription Page ${lock.subscription_page}`);
console.log(`Wrote ${path.relative(repoRoot, targetEnvPath)}`);
