import { afterEach, describe, expect, it, vi } from "vitest";

import { createBroadcastStore } from "./broadcastStore.svelte";

function makeSessionStorage(initial: Record<string, string> = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: vi.fn((key: string) => values.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      values.set(key, value);
    }),
  };
}

function makeStore(api = vi.fn()) {
  return createBroadcastStore({
    api,
    onToast: vi.fn(),
    at: (_key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || _key,
  });
}

describe("broadcastStore", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("refreshes old cached counts that do not carry email availability", async () => {
    const storage = makeSessionStorage({
      "remnawave-admin:broadcast-audience-counts": JSON.stringify({
        counts: { all: 1 },
        loadedAt: Date.now(),
      }),
    });
    vi.stubGlobal("window", { sessionStorage: storage });
    const api = vi.fn().mockResolvedValue({
      ok: true,
      counts: { all: 2 },
      email_enabled: true,
    });
    const store = makeStore(api);

    expect(store.broadcastEmailAvailabilityKnown).toBe(false);

    await store.loadCounts();

    expect(api).toHaveBeenCalledWith("/admin/broadcast/audience-counts");
    expect(store.broadcastCounts?.all).toBe(2);
    expect(store.broadcastEmailAvailable).toBe(true);
    expect(store.broadcastEmailAvailabilityKnown).toBe(true);
  });

  it("allows email channel before the availability check completes", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      queued: 0,
      failed: 0,
      email_queued: 1,
      channels: ["email"],
    });
    const store = makeStore(api);
    store.updateField({
      broadcastTelegramEnabled: false,
      broadcastEmailEnabled: true,
      broadcastText: "Hello",
    });

    expect(store.canSubmit()).toBe(true);

    await store.runBroadcast();

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(payload.channels).toEqual(["email"]);
  });
});
