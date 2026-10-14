import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { selectBrowserPort } from "./ports.mjs";

// A fresh server must not reuse somebody else's demo or a reserved Windows port.
const env = { ...process.env };
try {
  env.PORT = String(await selectBrowserPort(env.PORT));
} catch (error) {
  console.error(error.message);
  process.exit(1);
}
console.log("Playwright demo port: " + env.PORT);
const child = spawn(
  process.execPath,
  [
    fileURLToPath(new URL("../node_modules/@playwright/test/cli.js", import.meta.url)),
    "test",
    ...process.argv.slice(2),
  ],
  { env, stdio: "inherit", windowsHide: true }
);
child.once("error", (error) => {
  console.error(error.message);
  process.exitCode = 1;
});
child.once("exit", (code) => {
  process.exitCode = code ?? 1;
});
