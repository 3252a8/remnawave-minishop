import { describe, expect, it, vi } from "vitest";

import { createInstallGuidesStore } from "./installGuidesStore";

const available = {
  ok: true,
  enabled: true,
  config: { version: "1", platforms: { windows: { apps: [{ name: "Happ" }] } } },
  source: "panel",
};

function makeStore(api = vi.fn()) {
  return createInstallGuidesStore({ api, t: (key) => key, showToast: vi.fn() });
}

describe("installGuidesStore", () => {
  it("retries a failed request when the install screen is reopened", async () => {
    const api = vi.fn().mockRejectedValueOnce(new Error("Network unavailable"));
    api.mockResolvedValueOnce(available);
    const store = makeStore(api);

    await store.load();
    expect(store.error).toBe("Network unavailable");
    await store.load();

    expect(api).toHaveBeenCalledTimes(2);
    expect(store.enabled).toBe(true);
    expect(store.error).toBe("");
    expect(store.config).toEqual(available.config);
    await store.load();
    expect(api).toHaveBeenCalledTimes(2);
  });

  it("retries an unavailable panel config instead of caching its error forever", async () => {
    const api = vi.fn().mockResolvedValueOnce({
      ok: true,
      enabled: false,
      config: null,
      error: "Panel service is unavailable",
    });
    api.mockResolvedValueOnce(available);
    const store = makeStore(api);

    await store.load();
    await store.load();

    expect(api).toHaveBeenCalledTimes(2);
    expect(store.enabled).toBe(true);
  });

  it("keeps an explicitly disabled configuration cached", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true, enabled: false, config: null });
    const store = makeStore(api);
    await store.load();
    await store.load();
    expect(api).toHaveBeenCalledOnce();
  });

  it("retries a public link with the same subscription and coalesces requests", async () => {
    const api = vi.fn().mockRejectedValueOnce(new Error("Network unavailable"));
    const store = makeStore(api);
    const token = "a".repeat(32);
    await store.loadPublic(token);
    let resolve!: (value: typeof available) => void;
    api.mockImplementationOnce(() => new Promise((done) => (resolve = done)));

    const retry = store.retry();
    const concurrent = store.retry();
    expect(store.loading).toBe(true);
    expect(store.loaded).toBe(false);
    expect(api).toHaveBeenCalledTimes(2);
    expect(api).toHaveBeenNthCalledWith(2, `/subscription-guides/public/${token}`);
    resolve(available);
    await Promise.all([retry, concurrent]);
    expect(store.enabled).toBe(true);
  });
});
