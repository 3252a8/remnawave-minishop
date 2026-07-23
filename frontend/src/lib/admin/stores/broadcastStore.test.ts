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

  it("adds server-discovered audience options with localized labels", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      counts: { all: 2, "segment:priority": 1 },
      audiences: [
        {
          target: "segment:priority",
          label_key: "broadcast_target_priority",
          fallback_label: "Priority users",
          order: 10,
        },
      ],
      email_enabled: false,
    });
    const store = makeStore(api);

    await store.loadCounts();

    expect(store.BROADCAST_TARGET_OPTIONS).toContainEqual({
      value: "segment:priority",
      label: "Priority users",
    });
    expect(store.broadcastCounts?.["segment:priority"]).toBe(1);
  });

  it("keeps unavailable extension audiences visible as locked grouped options", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      counts: { all: 2 },
      audiences: [
        {
          target: "segment:licensed",
          label_key: "broadcast_target_licensed",
          fallback_label: "Licensed audience",
          group_label_key: "broadcast_audience_group_extensions",
          group_fallback_label: "Extensions",
          available: false,
          order: 10,
        },
      ],
      email_enabled: false,
    });
    const store = makeStore(api);

    await store.loadCounts();

    expect(store.BROADCAST_TARGET_OPTIONS).toContainEqual({
      value: "segment:licensed",
      label: "Licensed audience",
      group: "Extensions",
      disabled: true,
      locked: true,
    });
  });

  it("sends broadcast buttons with Telegram preview requests", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      rendered_text: "Hello",
      rendered_subject: null,
      unknown_shortcodes: [],
      length: 5,
      sent: true,
    });
    const store = makeStore(api);
    store.updateField({ broadcastText: "Hello" });
    store.addButton();
    store.updateButton(0, { label: "Open", url: "https://example.com" });

    await store.sendPreview("send_telegram");

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(api.mock.calls[0][0]).toBe("/admin/broadcast/preview");
    expect(payload.buttons).toEqual([
      { kind: "url", label: "Open", url: "https://example.com", promo_code: "" },
    ]);
  });
});
