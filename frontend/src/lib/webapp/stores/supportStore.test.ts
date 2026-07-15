import { describe, expect, it, vi } from "vitest";

import type { ApiClient } from "../publicApi.js";
import { createSupportStore } from "./supportStore.js";

function makeSupportStore() {
  const api = vi.fn(async (path: string, _options?: RequestInit) => {
    if (path === "/support/tickets/7/messages") {
      return {
        ok: true,
        ticket: { ticket_id: 7, status: "awaiting_admin" },
        message: { message_id: 11, body: "Please help" },
      };
    }
    if (path === "/support/unread") return { ok: true, unread: 0 };
    return { ok: true, tickets: [], counts: {} };
  });
  const store = createSupportStore({
    api: api as unknown as ApiClient["api"],
    t: (key: string) => key,
    showToast: vi.fn(),
  });
  store.openedTicketId = 7;
  store.openedTicket = { ticket_id: 7, status: "open" };
  return { api, store };
}

describe("supportStore", () => {
  it("ignores concurrent replies while the first request is in flight", async () => {
    const { api, store } = makeSupportStore();

    const results = await Promise.all([
      store.sendReply("Please help"),
      store.sendReply("Please help"),
    ]);

    const replyCalls = api.mock.calls.filter(
      ([path, options]) =>
        path === "/support/tickets/7/messages" &&
        (options as RequestInit | undefined)?.method === "POST"
    );
    expect(replyCalls).toHaveLength(1);
    expect(results).toEqual([true, false]);
    expect(store.messages).toHaveLength(1);
  });
});
