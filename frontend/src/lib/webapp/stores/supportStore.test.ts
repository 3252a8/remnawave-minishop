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
    if (path === "/support/tickets/7/typing") return { ok: true };
    if (path === "/support/unread") return { ok: true, unread: 0 };
    return { ok: true, tickets: [], counts: {} };
  });
  const apiBlob = vi.fn<ApiClient["apiBlob"]>().mockResolvedValue(new Blob(["image"]));
  const store = createSupportStore({
    api: api as unknown as ApiClient["api"],
    apiBlob,
    t: (key: string) => key,
    showToast: vi.fn(),
  });
  store.openedTicketId = 7;
  store.openedTicket = { ticket_id: 7, status: "open" };
  return { api, apiBlob, store };
}

function makeListStore(responses: unknown[]) {
  const api = vi.fn(async () => responses.shift() ?? { ok: true, tickets: [], counts: {} });
  const store = createSupportStore({
    api: api as unknown as ApiClient["api"],
    apiBlob: vi.fn() as unknown as ApiClient["apiBlob"],
    t: (key: string) => key,
    showToast: vi.fn(),
  });
  return { api, store };
}

describe("supportStore", () => {
  it("loads exact custom emoji IDs through the authenticated ticket-scoped API", async () => {
    const { apiBlob, store } = makeSupportStore();
    const signal = new AbortController().signal;
    const id = "5368324170671202286";
    await store.loadCustomEmojiMedia(7, id, signal);
    expect(apiBlob).toHaveBeenCalledExactlyOnceWith(`/support/tickets/7/emoji/${id}`, { signal });
  });

  it.each([
    ["../7", "5368324170671202286"],
    ["0", "5368324170671202286"],
    ["7", "0"],
    ["7", "5368324170671202286/../../secret"],
  ])(
    "rejects unsafe ticket/emoji identifiers before requesting media: %s / %s",
    async (ticket, id) => {
      const { apiBlob, store } = makeSupportStore();
      await expect(
        store.loadCustomEmojiMedia(ticket, id, new AbortController().signal)
      ).rejects.toThrow("invalid_custom_emoji");
      expect(apiBlob).not.toHaveBeenCalled();
    }
  );

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

  it("signals typing without posting a ticket message", async () => {
    const { api, store } = makeSupportStore();

    store.notifyTyping(true);
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith("/support/tickets/7/typing", {
        method: "POST",
        body: JSON.stringify({ typing: true }),
      })
    );
    store.notifyTyping(false);
    await vi.waitFor(() =>
      expect(api).toHaveBeenCalledWith("/support/tickets/7/typing", {
        method: "POST",
        body: JSON.stringify({ typing: false }),
      })
    );

    expect(api.mock.calls.filter(([path]) => path === "/support/tickets/7/messages")).toHaveLength(
      0
    );
  });

  it("tracks which filter the held ticket list belongs to", async () => {
    const { store } = makeListStore([
      { ok: true, tickets: [{ ticket_id: 1 }], counts: { active: 1, total: 1 } },
      { ok: true, tickets: [], counts: { active: 1, closed: 0, total: 1 } },
    ]);

    expect(store.loadedFilter).toBe("");

    await store.loadList();
    expect(store.loadedFilter).toBe("active");

    store.setStatusFilter("closed");
    expect(store.loadedFilter).toBe("active");
    await vi.waitFor(() => expect(store.loadedFilter).toBe("closed"));
  });

  it("zeroes ticket counts the API stopped reporting", async () => {
    const { store } = makeListStore([
      { ok: true, tickets: [], counts: { active: 1, awaiting_admin: 1, total: 1 } },
      { ok: true, tickets: [], counts: { active: 1, awaiting_user: 1, total: 1 } },
    ]);

    await store.loadList();
    expect(store.counts.awaiting_admin).toBe(1);

    await store.loadList({ force: true });
    expect(store.counts).toMatchObject({ awaiting_admin: 0, awaiting_user: 1, active: 1 });
  });
});
