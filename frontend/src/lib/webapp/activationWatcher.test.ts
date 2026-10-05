import { afterEach, describe, expect, it, vi } from "vitest";

import { createActivationWatcher } from "./activationWatcher";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("createActivationWatcher", () => {
  it.each([false, true])("stops on a paid review without activation (paid=%s)", async (paid) => {
    vi.useFakeTimers();
    vi.stubGlobal("window", globalThis);
    let pending = true;
    const clearPending = vi.fn(() => {
      pending = false;
    });
    const fetchPaymentStatus = vi.fn(async () => ({ paid, status: "succeeded_pending_review" }));
    const loadData = vi.fn(async () => ({}));
    const maybeShowActivationSuccessDialog = vi.fn(async () => false);
    const onPaymentReview = vi.fn();
    const watcher = createActivationWatcher({
      activationHandoff: {
        clearPending,
        hasPending: () => pending,
        read: () => ({ pending: { paymentId: "payment-review" } }),
      },
      billing: { fetchPaymentStatus },
      canRefreshOnResume: () => true,
      getData: () => ({}),
      loadData,
      maybeShowActivationSuccessDialog,
      onPaymentReview,
      shouldWatch: () => true,
      intervalMs: 10,
    });

    watcher.start();
    await vi.advanceTimersByTimeAsync(100);
    await watcher.refreshOnResume();
    watcher.start();
    await vi.advanceTimersByTimeAsync(100);

    expect(fetchPaymentStatus).toHaveBeenCalledOnce();
    expect(clearPending).toHaveBeenCalledOnce();
    expect(onPaymentReview).toHaveBeenCalledOnce();
    expect(loadData).not.toHaveBeenCalled();
    expect(maybeShowActivationSuccessDialog).not.toHaveBeenCalled();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps polling finalization and activates only after fulfillment", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("window", globalThis);
    const fetchPaymentStatus = vi
      .fn()
      .mockResolvedValueOnce({ paid: true, status: "succeeded_pending_finalization" })
      .mockResolvedValue({ paid: true, status: "succeeded" });
    const loadData = vi.fn(async () => ({}));
    const maybeShowActivationSuccessDialog = vi.fn(async () => true);
    const watcher = createActivationWatcher({
      activationHandoff: {
        clearPending: vi.fn(),
        hasPending: () => true,
        read: () => ({ pending: { paymentId: "payment-finalizing" } }),
      },
      billing: { fetchPaymentStatus },
      canRefreshOnResume: () => true,
      getData: () => ({}),
      loadData,
      maybeShowActivationSuccessDialog,
      shouldWatch: () => true,
      intervalMs: 10,
    });

    await watcher.refreshOnResume();
    expect(loadData).not.toHaveBeenCalled();
    expect(maybeShowActivationSuccessDialog).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(10);
    expect(loadData).toHaveBeenCalledOnce();
    expect(maybeShowActivationSuccessDialog).toHaveBeenCalledOnce();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("stops a review discovered on resume before refreshing the profile", async () => {
    const clearPending = vi.fn();
    const onPaymentReview = vi.fn();
    const loadData = vi.fn(async () => ({}));
    const maybeShowActivationSuccessDialog = vi.fn(async () => true);
    const watcher = createActivationWatcher({
      activationHandoff: {
        clearPending,
        hasPending: () => true,
        read: () => ({ pending: { paymentId: "payment-review" } }),
      },
      billing: { fetchPaymentStatus: vi.fn(async () => ({ status: "succeeded_pending_review" })) },
      canRefreshOnResume: () => true,
      getData: () => ({}),
      loadData,
      maybeShowActivationSuccessDialog,
      onPaymentReview,
      shouldWatch: () => true,
    });

    await watcher.refreshOnResume();
    expect(clearPending).toHaveBeenCalledOnce();
    expect(onPaymentReview).toHaveBeenCalledOnce();
    expect(loadData).not.toHaveBeenCalled();
    expect(maybeShowActivationSuccessDialog).not.toHaveBeenCalled();
  });

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
