import { afterEach, describe, expect, it, vi } from "vitest";

import {
  expectedTicketCount,
  readSupportCountsHint,
  writeSupportCountsHint,
} from "./supportListHint.js";

const STORAGE_KEY = "rw_webapp_support_counts_v1:42";

function installStorage() {
  const store = new Map<string, string>();
  const localStorage = {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, String(value));
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key);
    }),
  };
  vi.stubGlobal("window", { localStorage });
  return { localStorage, store };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("support counts hint", () => {
  it("round-trips the counts of a scope", () => {
    installStorage();

    writeSupportCountsHint(42, { active: 2, closed: 1, awaiting_admin: 2, total: 3 });

    expect(readSupportCountsHint(42)).toEqual({
      active: 2,
      awaiting_admin: 2,
      awaiting_user: 0,
      closed: 1,
      open: 0,
      total: 3,
    });
  });

  it("keeps scopes apart and reports an unseen scope as unknown", () => {
    installStorage();

    writeSupportCountsHint(42, { active: 2, total: 2 });

    expect(readSupportCountsHint(7)).toBeNull();
  });

  it("normalizes junk counts to zero", () => {
    installStorage();

    writeSupportCountsHint(42, { active: -4, closed: "3", total: "oops" });

    expect(readSupportCountsHint(42)).toMatchObject({ active: 0, closed: 3, total: 0 });
  });

  it("drops an expired snapshot", () => {
    const { store } = installStorage();
    const staleAt = Date.now() - 15 * 24 * 60 * 60 * 1000;
    store.set(STORAGE_KEY, JSON.stringify({ updatedAt: staleAt, counts: { active: 3, total: 3 } }));

    expect(readSupportCountsHint(42)).toBeNull();
    expect(store.has(STORAGE_KEY)).toBe(false);
  });

  it("discards a corrupt snapshot", () => {
    const { store } = installStorage();
    store.set(STORAGE_KEY, "{not json");

    expect(readSupportCountsHint(42)).toBeNull();
    expect(store.has(STORAGE_KEY)).toBe(false);
  });

  it("skips storage entirely without a browser", () => {
    expect(readSupportCountsHint(42)).toBeNull();
    expect(() => writeSupportCountsHint(42, { active: 1 })).not.toThrow();
  });
});

describe("expectedTicketCount", () => {
  const counts = {
    active: 4,
    awaiting_admin: 3,
    awaiting_user: 1,
    closed: 2,
    open: 0,
    total: 6,
  };

  it("maps each tab onto its own count", () => {
    expect(expectedTicketCount(counts, "active")).toBe(4);
    expect(expectedTicketCount(counts, "awaiting_admin")).toBe(3);
    expect(expectedTicketCount(counts, "awaiting_user")).toBe(1);
    expect(expectedTicketCount(counts, "closed")).toBe(2);
    expect(expectedTicketCount(counts, "all")).toBe(6);
    expect(expectedTicketCount(counts, "")).toBe(6);
  });

  it("stays unknown without counts or for an unmapped filter", () => {
    expect(expectedTicketCount(null, "active")).toBeNull();
    expect(expectedTicketCount(counts, "resolved")).toBeNull();
  });
});
