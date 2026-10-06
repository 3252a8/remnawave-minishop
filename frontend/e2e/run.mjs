import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { fileURLToPath } from "node:url";

// A fresh server must not reuse somebody else's demo or a reserved Windows port.
const env = { ...process.env };
if (!env.PORT) {
  const server = createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  env.PORT = String(server.address().port);
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
}
const child = spawn(process.execPath, [
  fileURLToPath(new URL("../node_modules/@playwright/test/cli.js", import.meta.url)),
  "test", ...process.argv.slice(2),
], { env, stdio: "inherit", windowsHide: true });
child.once("error", (error) => { console.error(error.message); process.exitCode = 1; });
child.once("exit", (code) => { process.exitCode = code ?? 1; });
