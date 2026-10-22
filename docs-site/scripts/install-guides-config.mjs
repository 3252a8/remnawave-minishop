import { readFile } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";

const configUrl =
  "https://raw.githubusercontent.com/legiz-ru/my-remnawave/main/sub-page/subpage-config/multiapp.json";

export async function installGuidesConfigPayload({
  configFile,
  fetchConfig = fetch,
  wait = delay,
} = {}) {
  if (configFile) {
    // Explicit fixtures must fail on missing/invalid data, never fall back to the network.
    const config = JSON.parse(await readFile(configFile, "utf8"));
    return `${JSON.stringify(config, null, 2)}\n`;
  }

  let lastError;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    try {
      const response = await fetchConfig(configUrl, {
        headers: { accept: "application/json" },
        // Covers both connection establishment and reading the JSON response body.
        signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) {
        throw new Error(
          `Unable to download demo install guides config (${response.status} ${response.statusText})`,
        );
      }
      return `${JSON.stringify(await response.json(), null, 2)}\n`;
    } catch (error) {
      lastError = error;
      if (attempt < 3) await wait(500 * attempt);
    }
  }
  throw lastError;
}
