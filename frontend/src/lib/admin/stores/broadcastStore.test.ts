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
    expect(payload.exclude_blocked_telegram).toBeNull();
  });

  it("preserves a negative internal user id for an email-only message", async () => {
    const api = vi.fn().mockResolvedValue({ ok: true });
    const store = makeStore(api);

    expect(
      await store.sendToUser({
        userId: -1351969585506524,
        text: "Hello",
        channels: ["email"],
        emailSubject: "News",
        buttons: [],
      })
    ).toBeNull();

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(payload.target).toBe("user:-1351969585506524");
    expect(payload.channels).toEqual(["email"]);
  });

  it("uses the server-side blocked-recipient default for broadcasts", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      queued: 1,
      failed: 0,
      email_queued: 0,
      channels: ["telegram"],
    });
    const store = makeStore(api);
    store.updateField({ broadcastText: "Hello" });

    await store.runBroadcast();

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(payload.exclude_blocked_telegram).toBeNull();
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
      {
        kind: "url",
        label: "Open",
        labels: {},
        url: "https://example.com",
        promo_code: "",
        section: "",
      },
    ]);
  });

  it("normalizes Telegram shortcuts in ordinary link buttons", async () => {
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
    store.updateButton(0, { label: "Support", url: "@help_center" });

    await store.sendPreview("send_telegram");

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(payload.buttons[0].url).toBe("https://t.me/help_center");
  });

  it("uses the first localized draft when previewing before a language is selected", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      rendered_text: "Привет",
      rendered_subject: null,
      unknown_shortcodes: [],
      length: 6,
      sent: true,
    });
    const store = makeStore(api);
    store.updateField({ broadcastTexts: { ru: "Привет" } });

    await store.sendPreview("send_telegram");

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(payload.text).toBe("Привет");
  });

  it("keeps codes owned by a customer in their own dropdown group, below the shared ones", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      promos: [
        { code: "SOLO", is_active: true, max_activations: 1, current_activations: 0, user_id: 42 },
        { code: "SALE10", is_active: true, max_activations: 100, current_activations: 5 },
        // One allowed activation without an owner is an ordinary shared code.
        { code: "ONCE", is_active: true, max_activations: 1, current_activations: 0 },
      ],
    });
    const store = makeStore(api);

    await store.loadPromoOptions();

    expect(store.broadcastPromoOptions).toEqual([
      { value: "SALE10", label: "SALE10 · 5/100", group: "Shared codes" },
      { value: "ONCE", label: "ONCE · 0/1", group: "Shared codes" },
      { value: "SOLO", label: "SOLO · 0/1", group: "Personal codes" },
    ]);
    expect(api).toHaveBeenCalledWith("/admin/promos/options");
  });

  it("keeps shared suggestions before personal suggestions while searching", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      promos: [
        { code: "PERSONAL", max_activations: 1, current_activations: 0, user_id: 42 },
        { code: "PERSONAL-SHARED", max_activations: 20, current_activations: 0, user_id: null },
      ],
    });
    const store = makeStore(api);

    await store.loadPromoOptions("personal");

    expect(api).toHaveBeenCalledWith("/admin/promos/options?query=personal");
    expect(store.broadcastPromoOptions.map((option) => option.value)).toEqual([
      "PERSONAL-SHARED",
      "PERSONAL",
    ]);
  });

  it("ignores suggestions from an older search that finishes last", async () => {
    let resolveOld: (value: unknown) => void = () => {};
    let resolveNew: (value: unknown) => void = () => {};
    const api = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveOld = resolve;
          })
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveNew = resolve;
          })
      );
    const store = makeStore(api);

    const oldSearch = store.loadPromoOptions("old");
    const newSearch = store.loadPromoOptions("new");
    resolveNew({
      ok: true,
      promos: [{ code: "NEW", max_activations: 10, current_activations: 0, user_id: null }],
    });
    await newSearch;
    resolveOld({
      ok: true,
      promos: [{ code: "OLD", max_activations: 10, current_activations: 0, user_id: null }],
    });
    await oldSearch;

    expect(store.broadcastPromoOptions.map((option) => option.value)).toEqual(["NEW"]);
  });

  it("keeps manual promo entry available when suggestions fail", async () => {
    const api = vi.fn().mockResolvedValue({ ok: false, error: "unavailable" });
    const store = makeStore(api);

    await store.loadPromoOptions("manual");

    expect(store.broadcastPromoOptions).toEqual([]);
    expect(store.broadcastPromoOptionsLoaded).toBe(true);
    expect(store.broadcastPromoOptionsLoading).toBe(false);
  });

  it("sends a future ISO timestamp for a scheduled broadcast", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      queued: 0,
      failed: 0,
      email_queued: 0,
      channels: ["telegram"],
      broadcast: {
        broadcast_id: 7,
        status: "scheduled",
        target: "all",
        channels: ["telegram"],
        texts: { ru: "Позже" },
        email_subjects: {},
        buttons: [],
        scheduled_at: "2031-05-20T11:30:00.000Z",
        created_at: "2031-05-20T10:00:00.000Z",
        updated_at: "2031-05-20T10:00:00.000Z",
      },
    });
    const store = makeStore(api);
    store.updateField({
      broadcastText: "Later",
      broadcastScheduleEnabled: true,
      broadcastScheduledAt: "2031-05-20T14:30",
    });

    await store.runBroadcast();

    const payload = JSON.parse(api.mock.calls[0][1].body);
    expect(new Date(payload.scheduled_at).getTime()).toBe(new Date("2031-05-20T14:30").getTime());
    expect(store.broadcastHistory[0]?.status).toBe("scheduled");
    expect(store.broadcastScheduleEnabled).toBe(false);
  });

  it("loads, reschedules, and removes history entries", async () => {
    const item = {
      broadcast_id: 12,
      status: "scheduled",
      target: "active",
      channels: ["telegram"],
      texts: { en: "Hello" },
      email_subjects: {},
      buttons: [],
      scheduled_at: "2031-05-20T11:30:00.000Z",
      created_at: "2031-05-20T10:00:00.000Z",
      updated_at: "2031-05-20T10:00:00.000Z",
      recipient_count: 0,
      total_deliveries: 0,
      successful_deliveries: 0,
      failed_deliveries: 0,
      telegram_sent: 0,
      telegram_failed: 0,
      email_sent: 0,
      email_failed: 0,
    };
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, broadcasts: [item] })
      .mockResolvedValueOnce({
        ok: true,
        ...item,
        scheduled_at: "2031-05-21T09:00:00.000Z",
      })
      .mockResolvedValueOnce({ ok: true, deleted: true, broadcast_id: 12 });
    const store = makeStore(api);

    await store.loadHistory();
    expect(store.broadcastHistory[0]?.broadcastId).toBe(12);

    expect(await store.rescheduleBroadcast(12, "2020-01-01T00:00")).toBe(false);
    expect(api).toHaveBeenCalledTimes(1);

    expect(await store.rescheduleBroadcast(12, "2031-05-21T12:00")).toBe(true);
    expect(api.mock.calls[1][0]).toBe("/admin/broadcasts/12");
    expect(api.mock.calls[1][1].method).toBe("PATCH");

    await store.deleteBroadcast(12);
    expect(api.mock.calls[2][1].method).toBe("DELETE");
    expect(store.broadcastHistory).toEqual([]);
  });
});
