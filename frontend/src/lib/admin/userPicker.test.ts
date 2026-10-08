import { describe, expect, it } from "vitest";
import { createUserPicker } from "./userPicker.svelte";

describe("paged account selection", () => {
  it("discards stale search results and clears choices after a failed load", async () => {
    let resolveOld!: (page: { users: { user_id: number }[]; total: number }) => void;
    const old = new Promise<{ users: { user_id: number }[]; total: number }>((resolve) => {
      resolveOld = resolve;
    });
    const picker = createUserPicker(async (query) => {
      if (!query) return old;
      if (query === "error") throw Error("unavailable");
      return { users: [{ user_id: 2 }], total: 1 };
    });
    const pending = picker.load();
    picker.changeQuery("new");
    await picker.load();
    resolveOld({ users: [{ user_id: 1 }], total: 1 });
    await pending;
    expect(picker.users).toEqual([{ user_id: 2 }]);
    picker.changeQuery("error");
    expect(picker.users).toEqual([]);
    await picker.load();
    expect(picker.users).toEqual([]);
    expect(picker.failed).toBe(true);
    expect(picker.total).toBeNull();
  });
  it("uses committed query for pages and invalidates a disposed list", async () => {
    const requests: Array<[string, number]> = [];
    const picker = createUserPicker(async (query, page) => {
      requests.push([query, page]);
      return { users: [{ user_id: page + 1 }], total: 26, page, page_size: 25 };
    });
    picker.changeQuery(" email@example.com ");
    await picker.load();
    expect(picker.pageCount).toBe(2);
    await picker.load(1);
    expect(requests).toEqual([
      ["email@example.com", 0],
      ["email@example.com", 1],
    ]);
    const pending = picker.load();
    picker.dispose();
    await pending;
    expect(picker.users).toEqual([]);
  });
});
