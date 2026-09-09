import { describe, expect, it, vi } from "vitest";

import { createSubscriptionReissueAction } from "./subscriptionReissueAction";

type Harness = ReturnType<typeof createHarness>;

function createHarness(postResult: unknown, options: { reject?: boolean } = {}) {
  let busy = false;
  let dialogOpen = true;
  const calls: string[] = [];
  const showToast = vi.fn();
  const loadData = vi.fn(async () => {
    calls.push("loadData");
  });
  const refreshDevices = vi.fn(async () => {
    calls.push("refreshDevices");
  });
  const postSubscriptionReissue = vi.fn(async () => {
    calls.push("post");
    if (options.reject) throw postResult;
    return postResult as never;
  });
  const action = createSubscriptionReissueAction({
    billing: { postSubscriptionReissue },
    getBusy: () => busy,
    loadData,
    refreshDevices,
    setBusy: (value) => {
      busy = value;
    },
    setDialogOpen: (open) => {
      dialogOpen = open;
    },
    showToast,
    t: (key) => key,
  });
  return {
    action,
    calls,
    loadData,
    postSubscriptionReissue,
    refreshDevices,
    showToast,
    getBusy: () => busy,
    getDialogOpen: () => dialogOpen,
    setBusy: (value: boolean) => {
      busy = value;
    },
  };
}

describe("createSubscriptionReissueAction", () => {
  it("posts, toasts the email confirmation, closes the dialog and refreshes data", async () => {
    const harness: Harness = createHarness({ ok: true, delivery_channel: "email" });

    await harness.action.confirmSubscriptionReissue();

    expect(harness.postSubscriptionReissue).toHaveBeenCalledTimes(1);
    expect(harness.showToast).toHaveBeenCalledWith("wa_subscription_reissue_done");
    expect(harness.getDialogOpen()).toBe(false);
    expect(harness.calls).toEqual(["post", "loadData", "refreshDevices"]);
    expect(harness.getBusy()).toBe(false);
  });

  it("uses the Telegram confirmation when email delivery falls back", async () => {
    const harness = createHarness({ ok: true, delivery_channel: "telegram" });

    await harness.action.confirmSubscriptionReissue();

    expect(harness.showToast).toHaveBeenCalledWith("wa_subscription_reissue_done_telegram");
    expect(harness.getDialogOpen()).toBe(false);
  });

  it("uses the Mini App confirmation when no delivery channel is available", async () => {
    const harness = createHarness({ ok: true, delivery_channel: "app" });

    await harness.action.confirmSubscriptionReissue();

    expect(harness.showToast).toHaveBeenCalledWith("wa_subscription_reissue_done_app");
    expect(harness.getDialogOpen()).toBe(false);
  });

  it("maps subscription_not_active errors to the dedicated toast", async () => {
    const harness = createHarness({ ok: false, error: "subscription_not_active" });

    await harness.action.confirmSubscriptionReissue();

    expect(harness.showToast).toHaveBeenCalledWith("wa_subscription_reissue_requires_subscription");
  });

  it("falls back to the server message, then the generic failure toast", async () => {
    const withMessage = createHarness({ ok: false, error: "boom", message: "Panel exploded" });
    await withMessage.action.confirmSubscriptionReissue();
    expect(withMessage.showToast).toHaveBeenCalledWith("Panel exploded");

    const thrown = createHarness(new Error("network"), { reject: true });
    await thrown.action.confirmSubscriptionReissue();
    expect(thrown.showToast).toHaveBeenCalledWith("network");

    const opaque = createHarness({ ok: false }, {});
    await opaque.action.confirmSubscriptionReissue();
    expect(opaque.showToast).toHaveBeenCalledWith("wa_subscription_reissue_failed");
  });

  it("ignores confirm and close while busy, and open while busy", async () => {
    const harness = createHarness({ ok: true, delivery_channel: "email" });
    harness.setBusy(true);

    await harness.action.confirmSubscriptionReissue();
    harness.action.closeSubscriptionReissueDialog();
    harness.action.openSubscriptionReissueDialog();

    expect(harness.postSubscriptionReissue).not.toHaveBeenCalled();
    expect(harness.getDialogOpen()).toBe(true);
  });

  it("opens and closes the dialog when idle", () => {
    const harness = createHarness({ ok: true, delivery_channel: "email" });

    harness.action.closeSubscriptionReissueDialog();
    expect(harness.getDialogOpen()).toBe(false);

    harness.action.openSubscriptionReissueDialog();
    expect(harness.getDialogOpen()).toBe(true);
  });
});
