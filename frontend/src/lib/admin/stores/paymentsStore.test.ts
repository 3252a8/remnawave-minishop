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
