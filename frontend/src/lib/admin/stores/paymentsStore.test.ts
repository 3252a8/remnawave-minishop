import { describe, expect, it, vi } from "vitest";

import { createPaymentsStore } from "./paymentsStore.svelte";

describe("paymentsStore sorting", () => {
  it("requests the selected server sort and returns to the first page", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      payments: [],
      total: 0,
      page: 0,
      page_size: 25,
    });
    const store = createPaymentsStore({ api: api as never });

    store.setPage(3);
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(1));
    store.setSort("amount_asc");

    await vi.waitFor(() =>
      expect(api).toHaveBeenLastCalledWith("/admin/payments?page=0&page_size=25&sort=amount_asc")
    );
    expect(store.paymentsPage).toBe(0);
    expect(store.paymentsSort).toBe("amount_asc");
  });
});
