import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../../webapp/publicApi.js";
import { createAdminSupportStore } from "./supportStore.svelte";

async function makeSupportStore() {
  const api = vi.fn(async (path: string, _options?: RequestInit) => {
    if (path === "/admin/support/tickets/7") {
      return {
        ok: true,
        ticket: { ticket_id: 7, status: "open", unread_admin_count: 0 },
        messages: [],
        user_snapshot: {},
        peer_typing: false,
      };
    }
    if (path === "/admin/support/tickets/7/messages") {
      return {
        ok: true,
        ticket: { ticket_id: 7, status: "awaiting_user" },
        message: { message_id: 12, body: "We are checking" },
      };
    }
    if (path === "/admin/support/tickets/7/typing") return { ok: true };
    if (path === "/admin/support/stats?include_partner_attention=1") return { ok: true, stats: {} };
    return { ok: true, tickets: [] };
  });
  const apiBlob = vi.fn<ApiClient["apiBlob"]>().mockResolvedValue(new Blob(["image"]));
  const store = createAdminSupportStore({
    api: api as unknown as ApiClient["api"],
    apiBlob,
    at: (key: string) => key,
    onToast: vi.fn(),
  });
  await store.openTicket(7, { skipPush: true });
  return { api, apiBlob, store };
}

describe("admin supportStore", () => {
  it("shares the badge request and fetches fresh counts after concurrent ticket changes", async () => {
    let finish!: (value: object) => void;
    const api = vi
      .fn()
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          })
      )
      .mockResolvedValue({
        ok: true,
        stats: { total_unread_admin: 4, partner_attention_total: 6 },
      });
    const store = createAdminSupportStore({
      api: api as unknown as ApiClient["api"],
      apiBlob: vi.fn(),
      at: (key) => key,
      onToast: vi.fn(),
    });
    const initial = store.loadStats();
    const duplicate = store.loadStats();
    const mutation = store.loadStats(true);
    const secondMutation = store.loadStats(true);
    expect(api.mock.calls).toEqual([["/admin/support/stats?include_partner_attention=1"]]);
    finish({ ok: true, stats: { total_unread_admin: 5, partner_attention_total: 2 } });
    await Promise.all([initial, duplicate, mutation, secondMutation]);
    expect(api).toHaveBeenCalledTimes(2);
    expect(store.stats).toMatchObject({ total_unread_admin: 4, partner_attention_total: 6 });
  });

  it("pauses badge polling while hidden and refreshes once on return", async () => {
    const fakeDocument = Object.assign(new EventTarget(), { visibilityState: "hidden" });
    const fakeWindow = Object.assign(new EventTarget(), { setInterval, clearInterval });
    vi.stubGlobal("document", fakeDocument);
    vi.stubGlobal("window", fakeWindow);
    const api = vi.fn().mockResolvedValue({ ok: true, stats: {} });
    const store = createAdminSupportStore({
      api: api as unknown as ApiClient["api"],
      apiBlob: vi.fn(),
      at: (key) => key,
      onToast: vi.fn(),
    });
    try {
      store.startStatsPolling();
      expect(api).not.toHaveBeenCalled();
      fakeDocument.visibilityState = "visible";
      fakeDocument.dispatchEvent(new Event("visibilitychange"));
      fakeWindow.dispatchEvent(new Event("focus"));
      expect(api).toHaveBeenCalledTimes(1);
      await store.loadStats();
      store.stopStatsPolling();
      fakeWindow.dispatchEvent(new Event("pageshow"));
      expect(api).toHaveBeenCalledTimes(1);
    } finally {
      store.stopStatsPolling();
      vi.unstubAllGlobals();
    }
  });

  it("loads custom emoji through the authenticated admin media API", async () => {
    const { apiBlob, store } = await makeSupportStore();
    const signal = new AbortController().signal;
    const id = "5368324170671202286";
    await store.loadCustomEmojiMedia(id, signal);
    expect(apiBlob).toHaveBeenCalledExactlyOnceWith(`/admin/telegram-emoji/media/${id}`, {
      signal,
    });
  });

  it.each(["0", "01", "5368324170671202286/../../secret", '1" onclick="alert(1)'])(
    "never requests admin media for an unsafe identifier: %s",
    async (id) => {
      const { apiBlob, store } = await makeSupportStore();
      await expect(store.loadCustomEmojiMedia(id, new AbortController().signal)).rejects.toThrow(
        "invalid_custom_emoji"
      );
      expect(apiBlob).not.toHaveBeenCalled();
    }
  );

  it.each(["awaiting_admin", "awaiting_user"])(
    "requests only %s tickets for the selected status view",
    async (status) => {
      const { api, store } = await makeSupportStore();
      api.mockClear();

      store.setStatusView(status);

      await vi.waitFor(() =>
        expect(api).toHaveBeenCalledWith(
          `/admin/support/tickets?limit=50&offset=0&status=${status}&sort=importance_desc`
        )
      );
      expect(store.filters.status).toBe(status);
    }
  );

  it("ignores concurrent replies while the first request is in flight", async () => {
    const { api, store } = await makeSupportStore();

    const results = await Promise.all([
      store.sendReply("We are checking"),
      store.sendReply("We are checking"),
    ]);

    expect(
      api.mock.calls.filter(([path]) => path === "/admin/support/tickets/7/messages")
    ).toHaveLength(1);
    expect(results).toEqual([true, false]);
    expect(store.messages).toHaveLength(1);
  });

  it("signals public replies but hides internal-note typing", async () => {
    const { api, store } = await makeSupportStore();

    store.notifyTyping(true);
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith("/admin/support/tickets/7/typing", {
        method: "POST",
        body: JSON.stringify({ typing: true }),
      })
    );

    store.toggleInternalNote();
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith("/admin/support/tickets/7/typing", {
        method: "POST",
        body: JSON.stringify({ typing: false }),
      })
    );
    const typingCalls = api.mock.calls.filter(
      ([path]) => path === "/admin/support/tickets/7/typing"
    ).length;
    store.notifyTyping(true);
    await Promise.resolve();

    expect(
      api.mock.calls.filter(([path]) => path === "/admin/support/tickets/7/typing")
    ).toHaveLength(typingCalls);
  });
});
