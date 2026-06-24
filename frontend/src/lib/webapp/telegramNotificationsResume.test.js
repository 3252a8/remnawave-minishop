import { describe, expect, it, vi } from "vitest";

import { refreshTelegramNotificationsAfterResume } from "./telegramNotificationsResume.js";

function makeDeps(overrides = {}) {
  const state = {
    botOpenedAt: 100,
    lastCheckAt: 0,
    mode: "app",
    needPrompt: true,
    refreshBusy: false,
    ...overrides.state,
  };
  const deps = {
    cooldownMs: 60_000,
    loadData: vi.fn(async () => {}),
    now: vi.fn(() => 100_000),
    readState: vi.fn(() => state),
    setBotOpenedAt: vi.fn((openedAt) => {
      state.botOpenedAt = openedAt;
    }),
    setLastCheckAt: vi.fn((checkedAt) => {
      state.lastCheckAt = checkedAt;
    }),
    setRefreshBusy: vi.fn((busy) => {
      state.refreshBusy = busy;
    }),
    ...overrides.deps,
  };
  return { deps, state };
}

describe("refreshTelegramNotificationsAfterResume", () => {
  it("skips when the resume refresh is not needed", async () => {
    for (const state of [
      { mode: "login" },
      { needPrompt: false },
      { botOpenedAt: 0 },
      { refreshBusy: true },
    ]) {
      const { deps } = makeDeps({ state });

      await refreshTelegramNotificationsAfterResume(deps);

      expect(deps.loadData).not.toHaveBeenCalled();
    }
  });

  it("respects the refresh cooldown", async () => {
    const { deps } = makeDeps({ state: { lastCheckAt: 50_000 } });

    await refreshTelegramNotificationsAfterResume(deps);

    expect(deps.loadData).not.toHaveBeenCalled();
    expect(deps.setRefreshBusy).not.toHaveBeenCalled();
  });

  it("refreshes data and clears the opened marker once prompt disappears", async () => {
    const { deps, state } = makeDeps({
      deps: {
        loadData: vi.fn(async () => {
          state.needPrompt = false;
        }),
      },
    });

    await refreshTelegramNotificationsAfterResume(deps);

    expect(deps.setLastCheckAt).toHaveBeenCalledWith(100_000);
    expect(deps.setRefreshBusy).toHaveBeenNthCalledWith(1, true);
    expect(deps.loadData).toHaveBeenCalledOnce();
    expect(deps.setBotOpenedAt).toHaveBeenCalledWith(0);
    expect(deps.setRefreshBusy).toHaveBeenLastCalledWith(false);
  });

  it("swallows refresh failures and always clears the busy flag", async () => {
    const { deps } = makeDeps({
      deps: { loadData: vi.fn(async () => Promise.reject(new Error("boom"))) },
    });

    await refreshTelegramNotificationsAfterResume(deps);

    expect(deps.setRefreshBusy).toHaveBeenNthCalledWith(1, true);
    expect(deps.setRefreshBusy).toHaveBeenLastCalledWith(false);
  });
});
