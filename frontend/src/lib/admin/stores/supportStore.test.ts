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
    if (path === "/admin/support/stats") return { ok: true, stats: {} };
    return { ok: true, tickets: [] };
  });
  const store = createAdminSupportStore({
    api: api as unknown as ApiClient["api"],
    at: (key: string) => key,
    onToast: vi.fn(),
  });
  await store.openTicket(7, { skipPush: true });
  return { api, store };
}

describe("admin supportStore", () => {
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
