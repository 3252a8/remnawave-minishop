#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const envPath = process.env.REMNAWAVE_UPGRADE_ENV_PATH
  ? path.resolve(process.env.REMNAWAVE_UPGRADE_ENV_PATH)
  : path.join(repoRoot, ".env.remnawave-dev");
const supportPath = path.join(
  repoRoot,
  "backend",
  "bot",
  "services",
  "remnawave_support.json",
);
const sourceVersion = process.argv[2];
const targetVersion = process.argv[3];

function fail(message) {
  console.error(message);
  process.exit(1);
}

function parseEnv(text) {
  const values = new Map();
  for (const line of text.split(/\r?\n/)) {
    const match = /^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/.exec(line);
    if (match) values.set(match[1], match[2]);
  }
  return values;
}

if (!sourceVersion || !targetVersion) {
  fail("Usage: node scripts/prepare_remnawave_upgrade_target.mjs <from> <to>");
}
if (!fs.existsSync(envPath)) {
  fail(".env.remnawave-dev does not exist; select the source preset first");
}

const support = JSON.parse(fs.readFileSync(supportPath, "utf8"));
const upgrade = support.upgrade_paths.find(
  (item) => item.from === sourceVersion && item.to === targetVersion,
);
if (!upgrade || upgrade.status !== "certified" || upgrade.strategy !== "same-panel-database") {
  fail(`No certified same-database upgrade path ${sourceVersion} -> ${targetVersion}`);
}

const original = fs.readFileSync(envPath, "utf8").replace(/\r\n/g, "\n");
const current = parseEnv(original);
if (current.get("REMNAWAVE_STAND_PRESET") !== sourceVersion) {
  fail(
    `Expected source preset ${sourceVersion}, got ${current.get("REMNAWAVE_STAND_PRESET") ?? "<missing>"}`,
  );
}
if (current.get("REMNAWAVE_DEV_VERSION") !== sourceVersion) {
  fail(`REMNAWAVE_DEV_VERSION must be ${sourceVersion} before the upgrade`);
}
const databaseVolume = current.get("REMNAWAVE_DEV_DB_VOLUME");
if (!databaseVolume) fail("REMNAWAVE_DEV_DB_VOLUME is missing");

const replacements = new Map([
  ["REMNAWAVE_STAND_PRESET", `upgrade-${sourceVersion}-to-${targetVersion}`],
  ["REMNAWAVE_DEV_VERSION", targetVersion],
]);
const seen = new Set();
const output = original
  .split("\n")
  .map((line) => {
    const match = /^([A-Za-z_][A-Za-z0-9_]*)=/.exec(line);
    if (!match || !replacements.has(match[1])) return line;
    seen.add(match[1]);
    return `${match[1]}=${replacements.get(match[1])}`;
  })
  .filter((line) => !/^REMNAWAVE_UPGRADE_(FROM|TO|SOURCE_DB_VOLUME)=/.test(line));

for (const key of replacements.keys()) {
  if (!seen.has(key)) fail(`${key} is missing from .env.remnawave-dev`);
}
while (output.at(-1) === "") output.pop();
output.push(
  "",
  "# Same-database compatibility transition selected by prepare_remnawave_upgrade_target.mjs.",
  `REMNAWAVE_UPGRADE_FROM=${sourceVersion}`,
  `REMNAWAVE_UPGRADE_TO=${targetVersion}`,
  `REMNAWAVE_UPGRADE_SOURCE_DB_VOLUME=${databaseVolume}`,
  "",
);
fs.writeFileSync(envPath, output.join("\n"), "utf8");

const updated = parseEnv(output.join("\n"));
if (updated.get("REMNAWAVE_DEV_DB_VOLUME") !== databaseVolume) {
  fail("Refusing upgrade because the Remnawave database volume changed");
}
console.log(
  `Prepared Remnawave ${sourceVersion} -> ${targetVersion} on existing volume ${databaseVolume}`,
);
