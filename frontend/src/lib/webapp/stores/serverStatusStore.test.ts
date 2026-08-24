import { describe, expect, it, vi } from "vitest";

import {
  createServerStatusStore,
  shouldPollServerStatus,
  type ServerStatusData,
} from "./serverStatusStore.svelte";

function response(provider: "url" | "uptime-kuma" = "uptime-kuma") {
  return {
    ok: true as const,
    enabled: true,
    status: "operational" as const,
    sources: provider === "url" ? [] : [{ provider, status: "operational" as const, error: null }],
    groups: [],
    incidents: [],
    stale: false,
    externalUrl: "https://status.example.test",
    updatedAt: "2026-08-24T12:00:00Z",
  };
}

describe("server status store", () => {
  it("deduplicates concurrent requests", async () => {
    let resolveRequest!: (value: ReturnType<typeof response>) => void;
    const api = vi.fn(
      () => new Promise<ReturnType<typeof response>>((resolve) => (resolveRequest = resolve))
    );
    const store = createServerStatusStore(api as never);

    const first = store.refresh(true);
    const second = store.refresh(true);
    expect(api).toHaveBeenCalledOnce();
    resolveRequest(response());
    await expect(first).resolves.toMatchObject({ status: "operational" });
    await expect(second).resolves.toMatchObject({ status: "operational" });
  });

  it("polls embedded providers but not URL mode", async () => {
    vi.useFakeTimers();
    const embeddedApi = vi.fn().mockResolvedValue(response());
    const embedded = createServerStatusStore(embeddedApi as never, 60_000);
    embedded.start();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(embeddedApi).toHaveBeenCalledTimes(2);
    embedded.stop();

    const urlApi = vi.fn().mockResolvedValue(response("url"));
    const url = createServerStatusStore(urlApi as never, 60_000);
    url.start();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(urlApi).toHaveBeenCalledOnce();
    url.stop();
    vi.useRealTimers();
  });

  it("recognizes only enabled embedded responses as pollable", () => {
    const embedded = response() as ServerStatusData;
    expect(shouldPollServerStatus(embedded)).toBe(true);
    expect(shouldPollServerStatus({ ...embedded, enabled: false })).toBe(false);
    expect(shouldPollServerStatus(response("url") as ServerStatusData)).toBe(false);
  });
});
