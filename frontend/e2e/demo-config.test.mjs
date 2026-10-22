import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";

import { installGuidesConfigPayload } from "../../docs-site/scripts/install-guides-config.mjs";

const temporaryDirectories = [];
afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true }))
  );
});

describe("demo install guide configuration", () => {
  it("loads the complete browser fixture without any network request", async () => {
    const fetchConfig = vi.fn();
    const config = JSON.parse(
      await installGuidesConfigPayload({
        configFile: fileURLToPath(new URL("./fixtures/install-guides.json", import.meta.url)),
        fetchConfig,
      })
    );
    expect(config.locales).toContain("ru");
    expect(config.locales).toContain("en");
    expect(Object.keys(config.platforms).length).toBeGreaterThanOrEqual(6);
    for (const platform of Object.values(config.platforms)) {
      expect(platform.apps.length).toBeGreaterThan(0);
      expect(
        platform.apps.some((app) =>
          app.blocks.some((block) =>
            block.buttons.some((button) => button.type === "subscriptionLink")
          )
        )
      ).toBe(true);
    }
    expect(fetchConfig).not.toHaveBeenCalled();
  });

  it.each(["missing", "invalid"])(
    "fails for a %s explicit fixture without falling back",
    async (kind) => {
      const directory = await mkdtemp(path.join(tmpdir(), "minishop-demo-config-"));
      temporaryDirectories.push(directory);
      const configFile = path.join(directory, "config.json");
      if (kind === "invalid") await writeFile(configFile, "{", "utf8");
      const fetchConfig = vi.fn();
      await expect(installGuidesConfigPayload({ configFile, fetchConfig })).rejects.toThrow();
      expect(fetchConfig).not.toHaveBeenCalled();
    }
  );

  it("uses the remote configuration for ordinary documentation builds", async () => {
    const fetchConfig = vi.fn().mockResolvedValue(new Response('{"version":"1"}'));
    expect(JSON.parse(await installGuidesConfigPayload({ fetchConfig }))).toEqual({ version: "1" });
    expect(fetchConfig).toHaveBeenCalledOnce();
    expect(fetchConfig.mock.calls[0][0]).toMatch(/^https:\/\/raw\.githubusercontent\.com\//);
    expect(fetchConfig.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  });

  it.each(["network", "http", "json"])(
    "retries %s failures without hiding the final error",
    async (kind) => {
      const fetchConfig = vi.fn(() => {
        if (kind === "network") throw new Error("offline");
        return Promise.resolve(
          kind === "http"
            ? new Response("", { status: 503, statusText: "Unavailable" })
            : new Response("{")
        );
      });
      const wait = vi.fn().mockResolvedValue(undefined);
      await expect(installGuidesConfigPayload({ fetchConfig, wait })).rejects.toThrow();
      expect(fetchConfig).toHaveBeenCalledTimes(3);
      expect(wait.mock.calls).toEqual([[500], [1000]]);
    }
  );

  it("recovers from a transient response failure", async () => {
    const fetchConfig = vi
      .fn()
      .mockRejectedValueOnce(new Error("temporary"))
      .mockResolvedValueOnce(new Response('{"version":"1"}'));
    const wait = vi.fn().mockResolvedValue(undefined);
    expect(JSON.parse(await installGuidesConfigPayload({ fetchConfig, wait }))).toEqual({
      version: "1",
    });
    expect(fetchConfig).toHaveBeenCalledTimes(2);
    expect(wait).toHaveBeenCalledWith(500);
  });
});
