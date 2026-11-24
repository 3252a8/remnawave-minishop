import { QueryClient } from "@tanstack/svelte-query";
import { describe, expect, it, vi } from "vitest";

import { createStatsStore } from "./statsStore.svelte";

describe("dashboard statistics", () => {
  it("publishes local cards while panel requests are pending and reuses both on return", async () => {
    let finishPanel!: (value: unknown) => void;
    const panelResponse = new Promise((resolve) => (finishPanel = resolve));
    const local = { ok: true, users: { total_users: 3 } };
    const panel = { system: { onlineStats: { onlineNow: 2 } } };
    const api = vi.fn(async (path: string) => {
      if (path === "/admin/stats/panel") return panelResponse;
      if (path === "/admin/stats?include_panel=false") return local;
      throw new Error(path);
    });
    const queryClient = new QueryClient();
    const store = createStatsStore({
      api: api as never,
      queryClient,
      onToast: vi.fn(),
      at: String,
    });

    const first = store.loadStats();
    const second = store.loadStats();
    await vi.waitFor(() => expect(store.stats).toEqual(local));
    expect(store.statsLoading).toBe(false);
    expect(store.panelLoading).toBe(true);
    expect(store.panel).toBeNull();
    finishPanel({ ok: true, panel });
    await Promise.all([first, second]);
    expect(store.panel).toEqual(panel);

    const revisit = store.loadStats();
    expect(store.stats).toEqual(local);
    await revisit;
    expect(api).toHaveBeenCalledTimes(2);
    queryClient.clear();
  });

  it("keeps local data on a failed refresh and retries both sources after sync", async () => {
    const local = { ok: true, users: { total_users: 3 } };
    const api = vi
      .fn()
      .mockResolvedValueOnce(local)
      .mockRejectedValueOnce(new Error("Panel offline"))
      .mockRejectedValueOnce(new Error("Local query failed"))
      .mockResolvedValueOnce({ ok: true, panel: { system: {} } })
      .mockResolvedValueOnce({ ok: true, status: "queued" })
      .mockResolvedValueOnce({ ...local, users: { total_users: 4 } })
      .mockResolvedValueOnce({ ok: true, panel: null });
    const queryClient = new QueryClient();
    const store = createStatsStore({
      api: api as never,
      queryClient,
      onToast: vi.fn(),
      at: String,
    });

    await store.loadStats();
    expect(store.stats).toEqual(local);
    expect(store.panel).toEqual({ error: "unavailable" });
    await store.loadStats({ refresh: true });
    expect(store.stats).toEqual(local);
    expect(store.statsError).toBe("Local query failed");
    expect(store.panel).toEqual({ system: {} });

    await store.triggerSync();
    expect(api).toHaveBeenCalledWith("/admin/sync", { method: "POST" });
    expect(store.stats).toMatchObject({ users: { total_users: 4 } });
    expect(store.statsError).toBe("");
    expect(store.panel).toBeNull();
    queryClient.clear();
  });
});
