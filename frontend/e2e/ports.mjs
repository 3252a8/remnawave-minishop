import { randomInt } from "node:crypto";
import { createServer } from "node:net";

export const E2E_HOST = "127.0.0.1";
const DEFAULT_PORT = 8091;
const FIRST_DYNAMIC_PORT = 49152;
const LAST_PORT = 65535;
const MAX_ATTEMPTS = 128;

// Chromium's HTTP restrictions also apply to loopback addresses.
// https://github.com/chromium/chromium/blob/main/net/base/port_util.cc
const BLOCKED_PORTS = new Set([
  0, 1, 7, 9, 11, 13, 15, 17, 19, 20, 21, 22, 23, 25, 37, 42, 43, 53, 69, 77, 79, 87, 95, 101, 102,
  103, 104, 109, 110, 111, 113, 115, 117, 119, 123, 135, 137, 139, 143, 161, 179, 389, 427, 465,
  512, 513, 514, 515, 526, 530, 531, 532, 540, 548, 554, 556, 563, 587, 601, 636, 989, 990, 993,
  995, 1719, 1720, 1723, 2049, 3659, 4045, 5060, 5061, 6000, 6566, 6665, 6666, 6667, 6668, 6669,
  6697, 10080,
]);

export function browserPort(value) {
  const raw = value === undefined || value === "" ? String(DEFAULT_PORT) : String(value).trim();
  const port = Number(raw);
  if (!/^\d+$/.test(raw) || !Number.isInteger(port) || port < 1 || port > LAST_PORT) {
    throw new Error(
      "PORT must be an integer between 1 and 65535; received " + JSON.stringify(value)
    );
  }
  if (BLOCKED_PORTS.has(port)) {
    throw new Error(
      "PORT=" + port + " is blocked by Chromium for HTTP. Choose 8091 or unset PORT."
    );
  }
  return port;
}

async function probePort(port) {
  const server = createServer();
  try {
    await new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen({ port, host: E2E_HOST, exclusive: true }, resolve);
    });
    await new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  } finally {
    server.removeAllListeners();
  }
}

export async function selectBrowserPort(configuredPort) {
  if (configuredPort !== undefined && configuredPort !== "") {
    const port = browserPort(configuredPort);
    try {
      await probePort(port);
    } catch (error) {
      throw new Error(
        "Cannot bind configured PORT=" +
          port +
          " on " +
          E2E_HOST +
          ". Unset PORT for automatic selection.",
        { cause: error }
      );
    }
    return port;
  }

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
    // Do not delegate to listen(0): a customised OS range can return 6668.
    // Random probes spread across the range rather than getting stuck inside
    // a contiguous Windows excluded-port range.
    const port = randomInt(FIRST_DYNAMIC_PORT, LAST_PORT + 1);
    if (BLOCKED_PORTS.has(port)) continue;
    try {
      await probePort(port);
      return port;
    } catch (error) {
      if (error.code !== "EADDRINUSE" && error.code !== "EACCES") throw error;
    }
  }
  throw new Error(
    "No available browser-safe loopback port found after 128 attempts. Set PORT explicitly."
  );
}
