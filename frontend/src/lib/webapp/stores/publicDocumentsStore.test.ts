import { describe, expect, it, vi } from "vitest";

import { createPublicDocumentsStore } from "./publicDocumentsStore.svelte";

const response = {
  ok: true,
  documents: [
    {
      slug: "privacy",
      title: "Privacy policy",
      role: "privacy_policy",
      show_in_settings: true,
    },
  ],
};

describe("public documents store", () => {
  it("shares the pending request and retains resolved documents for later settings visits", async () => {
    let resolveRequest!: (value: typeof response) => void;
    const api = vi.fn(() => new Promise<typeof response>((resolve) => (resolveRequest = resolve)));
    const store = createPublicDocumentsStore(api as never);

    expect(store.documents).toBeNull();
    const firstVisit = store.load();
    const secondVisit = store.load();
    expect(secondVisit).toBe(firstVisit);
    await Promise.resolve();
    expect(api).toHaveBeenCalledExactlyOnceWith("/documents");
    resolveRequest(response);
    await firstVisit;
    expect(store.documents).toMatchObject([{ slug: "privacy", showInSettings: true }]);

    await store.load();
    expect(api).toHaveBeenCalledOnce();
    expect(store.documents).toHaveLength(1);
  });

  it("caches a successful empty list", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, documents: [] });
    const store = createPublicDocumentsStore(api as never);

    await store.load();
    await store.load();

    expect(store.documents).toEqual([]);
    expect(api).toHaveBeenCalledOnce();
  });

  it.each(["rejected request", "error envelope", "synchronous error"])(
    "uses legacy links after %s and retries on the next visit",
    async (failure) => {
      const api = vi.fn();
      if (failure === "rejected request") api.mockRejectedValueOnce(new Error("unavailable"));
      else if (failure === "error envelope") api.mockResolvedValueOnce({ ok: false });
      else
        api.mockImplementationOnce(() => {
          throw new Error("unavailable");
        });
      api.mockResolvedValueOnce(response);
      const store = createPublicDocumentsStore(api as never);

      await store.load();
      expect(store.documents).toEqual([]);
      const retry = store.load();
      expect(store.documents).toEqual([]);
      await retry;

      expect(api).toHaveBeenCalledTimes(2);
      expect(store.documents).toMatchObject([{ slug: "privacy" }]);
      await store.load();
      expect(api).toHaveBeenCalledTimes(2);
    }
  );

  it("keeps separate app instances isolated", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce(response)
      .mockResolvedValueOnce({ ok: true, documents: [] });
    const firstApp = createPublicDocumentsStore(api as never);
    const secondApp = createPublicDocumentsStore(api as never);

    await firstApp.load();
    expect(secondApp.documents).toBeNull();
    await secondApp.load();

    expect(api).toHaveBeenCalledTimes(2);
    expect(firstApp.documents).toHaveLength(1);
    expect(secondApp.documents).toEqual([]);
  });
});
