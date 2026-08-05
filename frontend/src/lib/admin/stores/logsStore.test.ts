import { describe, expect, it, vi } from "vitest";

import { createLogsStore } from "./logsStore.svelte";

describe("logsStore sorting", () => {
  it("keeps filtering while applying a global server sort", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      logs: [],
      total: 0,
      page: 0,
      page_size: 50,
    });
    const store = createLogsStore({ api: api as never });
    store.setFilter("42");

    store.setSort("event_desc");

    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith("/admin/logs?page=0&page_size=50&sort=event_desc&user_id=42")
    );
    expect(store.logsPage).toBe(0);
    expect(store.logsSort).toBe("event_desc");
  });
});
