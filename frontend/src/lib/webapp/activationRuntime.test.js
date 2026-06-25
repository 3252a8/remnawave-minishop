import { describe, expect, it, vi } from "vitest";

import { createActivationRuntime } from "./activationRuntime.js";

function makeRuntime(overrides = {}) {
  const state = {
    activationSuccessDialogOpen: false,
    activationSuccessUseInstallGuides: false,
    data: {
      subscription: { active: true, panel_uuid: "sub-1" },
      user: { user_id: 42 },
    },
    subscription: { active: true, connect_url: "https://example.test/connect" },
    handoffState: {
      pending: { startedAt: Date.now(), userKey: "42", paymentId: "pay-1" },
      acknowledged: null,
    },
    useInstallGuides: false,
    ...overrides.state,
  };
  const activationHandoff = {
    acknowledge: vi.fn((_subscriptionKey, _context, _payload, currentState) => {
      state.handoffState = { ...currentState, pending: null };
    }),
    hasPending: vi.fn(() => Boolean(state.handoffState.pending)),
    isAcknowledged: vi.fn(() => Boolean(state.handoffState.acknowledged)),
    isPendingFresh: vi.fn(() => true),
    pendingMatchesUser: vi.fn(() => true),
    read: vi.fn(() => state.handoffState),
    rememberPending: vi.fn(),
    subscriptionKey: vi.fn(() => "user|sub-1"),
    write: vi.fn((nextState) => {
      state.handoffState = nextState;
    }),
    ...overrides.activationHandoff,
  };
  const deps = {
    activationHandoff,
    closePaymentModal: vi.fn(),
    getActivationSuccessDialogOpen: () => state.activationSuccessDialogOpen,
    getActivationSuccessUseInstallGuides: () => state.activationSuccessUseInstallGuides,
    getData: () => state.data,
    getSubscription: () => state.subscription,
    canUseInstallGuides: () => state.useInstallGuides,
    loadInstallGuides: vi.fn(),
    openActivationConnectLink: vi.fn(),
    refreshPendingActivationOnResume: vi.fn(async () => {}),
    setActivationSuccessDialogOpen: vi.fn((open) => {
      state.activationSuccessDialogOpen = open;
    }),
    setActivationSuccessUseInstallGuides: vi.fn((useInstallGuides) => {
      state.activationSuccessUseInstallGuides = useInstallGuides;
    }),
    setActiveTab: vi.fn(),
    setScreen: vi.fn(),
    startPendingActivationWatch: vi.fn(),
    stopPendingActivationWatch: vi.fn(),
    syncAppSectionPath: vi.fn(),
    tick: vi.fn(async () => {}),
    ...overrides.deps,
  };
  return { deps, runtime: createActivationRuntime(deps), state };
}

describe("createActivationRuntime", () => {
  it("clears matching pending handoff when activation is already acknowledged", async () => {
    const { deps, runtime, state } = makeRuntime({
      state: {
        handoffState: {
          pending: { startedAt: 1, userKey: "42" },
          acknowledged: { subscriptionKey: "user|sub-1" },
        },
      },
    });

    expect(await runtime.maybeShowActivationSuccessDialog()).toBe(false);

    expect(deps.activationHandoff.write).toHaveBeenCalledWith({
      acknowledged: { subscriptionKey: "user|sub-1" },
      pending: null,
    });
    expect(state.activationSuccessDialogOpen).toBe(false);
    expect(deps.closePaymentModal).not.toHaveBeenCalled();
  });

  it("acknowledges and opens the success dialog for direct connect targets", async () => {
    const { deps, runtime, state } = makeRuntime();

    expect(await runtime.maybeShowActivationSuccessDialog({ force: true, source: "payment" })).toBe(
      true
    );

    expect(deps.activationHandoff.acknowledge).toHaveBeenCalledWith(
      "user|sub-1",
      { force: true, source: "payment" },
      state.data,
      expect.any(Object)
    );
    expect(deps.stopPendingActivationWatch).toHaveBeenCalledOnce();
    expect(deps.closePaymentModal).toHaveBeenCalledOnce();
    expect(deps.setActiveTab).toHaveBeenCalledWith("home");
    expect(deps.setScreen).toHaveBeenCalledWith("home");
    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("home", true);
    expect(state.activationSuccessDialogOpen).toBe(true);
  });

  it("navigates install-guide targets without opening connect links", () => {
    const { deps, runtime, state } = makeRuntime({
      state: { activationSuccessUseInstallGuides: true, useInstallGuides: true },
    });

    runtime.closeActivationSuccessDialog();

    expect(deps.setActivationSuccessDialogOpen).toHaveBeenCalledWith(false);
    expect(deps.closePaymentModal).toHaveBeenCalledOnce();
    expect(deps.setActiveTab).toHaveBeenCalledWith("home");
    expect(deps.setScreen).toHaveBeenCalledWith("install");
    expect(deps.syncAppSectionPath).toHaveBeenCalledWith("install", true);
    expect(deps.loadInstallGuides).toHaveBeenCalledWith(true);
    expect(deps.openActivationConnectLink).not.toHaveBeenCalled();
    expect(state.activationSuccessUseInstallGuides).toBe(true);
  });

  it("opens the activation connect link when closing a direct-connect dialog", () => {
    const { deps, runtime } = makeRuntime({
      state: { activationSuccessUseInstallGuides: false },
    });

    runtime.closeActivationSuccessDialog();

    expect(deps.setActivationSuccessDialogOpen).toHaveBeenCalledWith(false);
    expect(deps.openActivationConnectLink).toHaveBeenCalledOnce();
  });

  it("delegates remember and watcher helpers", async () => {
    const { deps, runtime, state } = makeRuntime();

    runtime.rememberActivationPending({ source: "payment" });
    runtime.startPendingActivationWatch();
    runtime.stopPendingActivationWatch();
    await runtime.refreshPendingActivationOnResume();

    expect(deps.activationHandoff.rememberPending).toHaveBeenCalledWith(
      { source: "payment" },
      state.data
    );
    expect(deps.startPendingActivationWatch).toHaveBeenCalledOnce();
    expect(deps.stopPendingActivationWatch).toHaveBeenCalledOnce();
    expect(deps.refreshPendingActivationOnResume).toHaveBeenCalledOnce();
  });
});
