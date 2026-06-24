import { describe, expect, it, vi } from "vitest";

import { createAutoRenewAction } from "./autoRenewAction.js";

function makeAction(overrides = {}) {
  let busy = Boolean(overrides.busy);
  const busyUpdates = [];
  const deps = {
    billing: {
      postAutoRenew: vi.fn(async () => ({ ok: true, auto_renew_enabled: true })),
    },
    getBusy: () => busy,
    loadData: vi.fn(async () => null),
    setBusy: vi.fn((nextBusy) => {
      busy = nextBusy;
      busyUpdates.push(nextBusy);
    }),
    showToast: vi.fn(),
    t: vi.fn((key) => key),
    ...overrides.deps,
  };
  return {
    action: createAutoRenewAction(deps),
    busyUpdates,
    deps,
  };
}

describe("createAutoRenewAction", () => {
  it("enables auto-renew and refreshes app data", async () => {
    const { action, busyUpdates, deps } = makeAction();

    await action.toggleAutoRenew(true);

    expect(deps.billing.postAutoRenew).toHaveBeenCalledWith(true);
    expect(deps.showToast).toHaveBeenCalledWith("wa_auto_renew_enabled");
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
    expect(busyUpdates).toEqual([true, false]);
  });

  it("uses the disabled success toast when the backend turns auto-renew off", async () => {
    const { action, deps } = makeAction({
      deps: {
        billing: {
          postAutoRenew: vi.fn(async () => ({ ok: true, auto_renew_enabled: false })),
        },
      },
    });

    await action.toggleAutoRenew(false);

    expect(deps.showToast).toHaveBeenCalledWith("wa_auto_renew_disabled");
  });

  it("guards concurrent updates while busy", async () => {
    const { action, deps } = makeAction({ busy: true });

    await action.toggleAutoRenew(true);

    expect(deps.billing.postAutoRenew).not.toHaveBeenCalled();
    expect(deps.setBusy).not.toHaveBeenCalled();
  });

  it("shows the saved-method requirement message", async () => {
    const { action, deps } = makeAction({
      deps: {
        billing: {
          postAutoRenew: vi.fn(async () => ({
            ok: false,
            error: "auto_renew_requires_saved_method",
          })),
        },
      },
    });

    await action.toggleAutoRenew(true);

    expect(deps.showToast).toHaveBeenCalledWith("wa_auto_renew_requires_saved_method");
    expect(deps.loadData).not.toHaveBeenCalled();
  });

  it("falls back to the generic update failure message", async () => {
    const { action, deps } = makeAction({
      deps: {
        billing: {
          postAutoRenew: vi.fn(async () => ({ ok: false })),
        },
      },
    });

    await action.toggleAutoRenew(true);

    expect(deps.showToast).toHaveBeenCalledWith("wa_auto_renew_update_failed");
  });
});
