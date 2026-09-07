import { describe, expect, it, vi } from "vitest";

import { copyPaymentText, createPaymentsStore } from "./paymentsStore.svelte";

describe("payment clipboard", () => {
  it("reports a copied value and exposes the value when copying is unavailable", async () => {
    const onToast = vi.fn();
    const copy = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(false);

    await copyPaymentText(710024, "Copied", onToast, copy);
    await copyPaymentText("provider-ref", "Copied", onToast, copy);

    expect(copy).toHaveBeenNthCalledWith(1, "710024");
    expect(copy).toHaveBeenNthCalledWith(2, "provider-ref");
    expect(onToast).toHaveBeenNthCalledWith(1, "Copied");
    expect(onToast).toHaveBeenNthCalledWith(2, "provider-ref");
  });
});

describe("paymentsStore sorting", () => {
  it("keeps a normalized search while paging and sorting and resets the page for a new user", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, payments: [], total: 0 });
    const store = createPaymentsStore({ api: api as never });
    store.setSearch("  alice@example.com  ");
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(1));
    store.setPage(2);
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(2));
    expect(api.mock.calls[1][0]).toContain(
      "page=2&page_size=25&sort=date_desc&search=alice%40example.com"
    );
    store.setSort("amount_asc");
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(3));
    expect(api.mock.calls[2][0]).toContain(
      "page=0&page_size=25&sort=amount_asc&search=alice%40example.com"
    );
    store.setSearch("");
    await vi.waitFor(() => expect(api).toHaveBeenCalledTimes(4));
    expect(api.mock.calls[3][0]).not.toContain("search=");
    expect(store.paymentsPage).toBe(0);
  });

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
