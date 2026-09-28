import { describe, expect, it, vi } from "vitest";

import { createAutoRenewAction } from "./autoRenewAction.js";

type TestOverrides = { busy?: boolean; deps?: Record<string, unknown> };

function makeAction(overrides: TestOverrides = {}) {
  let busy = Boolean(overrides.busy);
  const busyUpdates: boolean[] = [];
  const deps = {
    billing: {
      postAutoRenew: vi.fn(async () => ({ ok: true, auto_renew_enabled: true })),
    },
    getBusy: () => busy,
    loadData: vi.fn(async () => null),
    openExternalLink: vi.fn(),
    setCreatorCancelStep: vi.fn(),
    setBusy: vi.fn((nextBusy: boolean) => {
      busy = nextBusy;
      busyUpdates.push(nextBusy);
    }),
    showToast: vi.fn(),
    t: vi.fn((key: string) => key),
    ...overrides.deps,
  };
  return {
    action: createAutoRenewAction(deps as unknown as Parameters<typeof createAutoRenewAction>[0]),
    busyUpdates,
    deps,
  };
}

describe("createAutoRenewAction", () => {
  it("opens the Creator cancellation dialog without reporting disabled renewal", async () => {
    const { action, deps, busyUpdates } = makeAction({
      deps: {
        billing: {
          postAutoRenew: vi.fn(async () => ({
            ok: false,
            error: "auto_renew_tribute_cancel_required",
          })),
        },
      },
    });
    await action.toggleAutoRenew(false);
    expect(deps.setCreatorCancelStep).toHaveBeenCalledWith(1);
    expect(deps.openExternalLink).not.toHaveBeenCalled();
    expect(deps.showToast).not.toHaveBeenCalledWith("wa_auto_renew_disabled");
    expect(deps.loadData).not.toHaveBeenCalled();
    expect(busyUpdates).toEqual([true, false]);
  });

  it("requires a second confirmation before disabling local Creator renewal", async () => {
    const { action, deps } = makeAction({
      deps: {
        billing: {
          postAutoRenew: vi
            .fn()
            .mockResolvedValueOnce({ ok: false, error: "auto_renew_tribute_cancel_required" })
            .mockResolvedValueOnce({ ok: true, auto_renew_enabled: false }),
        },
      },
    });
    await action.toggleAutoRenew(false);
    action.openCreatorCancellationLink();
    action.openCreatorCancelConfirmation();
    expect(deps.openExternalLink).toHaveBeenCalledWith("https://t.me/tribute");
    expect(deps.setCreatorCancelStep).toHaveBeenLastCalledWith(2);
    expect(deps.billing.postAutoRenew).toHaveBeenCalledTimes(1);

    await action.confirmCreatorCancellation();
    expect(deps.billing.postAutoRenew).toHaveBeenLastCalledWith(false, true);
    expect(deps.setCreatorCancelStep).toHaveBeenLastCalledWith(0);
    expect(deps.loadData).toHaveBeenCalledWith({ fresh: true, preserveView: true });
  });

  it("keeps a Shop cancellation failure in the app", async () => {
    const { action, deps } = makeAction({
      deps: {
        billing: {
          postAutoRenew: vi.fn(async () => ({
            ok: false,
            error: "auto_renew_provider_cancel_failed",
          })),
        },
      },
    });
    await action.toggleAutoRenew(false);
    expect(deps.openExternalLink).not.toHaveBeenCalled();
    expect(deps.showToast).toHaveBeenCalledWith("wa_auto_renew_provider_cancel_failed");
  });

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
