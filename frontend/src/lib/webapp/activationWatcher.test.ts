import { afterEach, describe, expect, it, vi } from "vitest";

import { createActivationWatcher } from "./activationWatcher";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("createActivationWatcher", () => {
  it("does not rearm polling after it is stopped during an active check", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", globalThis);
    let resolveStatus: ((value: Record<string, unknown>) => void) | undefined;
    const fetchPaymentStatus = vi.fn(
      () =>
        new Promise<Record<string, unknown>>((resolve) => {
          resolveStatus = resolve;
        })
    );
    const watcher = createActivationWatcher({
      activationHandoff: {
        clearPending: vi.fn(),
        hasPending: () => true,
        read: () => ({ pending: { paymentId: "payment-1" } }),
      },
      billing: { fetchPaymentStatus },
      canRefreshOnResume: () => true,
      getData: () => ({}),
      loadData: vi.fn(async () => ({})),
      maybeShowActivationSuccessDialog: vi.fn(async () => false),
      shouldWatch: () => true,
      intervalMs: 10,
    });

    watcher.start();
    await vi.advanceTimersByTimeAsync(10);
    expect(fetchPaymentStatus).toHaveBeenCalledOnce();

    watcher.stop();
    resolveStatus?.({ paid: false });
    await Promise.resolve();
    await Promise.resolve();

    expect(vi.getTimerCount()).toBe(0);
  });
});
