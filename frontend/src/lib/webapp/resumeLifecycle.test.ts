import { describe, expect, it, vi } from "vitest";

import { createResumeLifecycle } from "./resumeLifecycle.js";
import { resetShellState, shellState } from "./shellState.svelte";
type TestOverrides = { [key: string]: Record<string, unknown> | undefined };

type Listener = () => void;

function makeTarget(extra: Record<string, unknown> = {}) {
  const listeners = new Map<string, Listener>();
  return {
    addEventListener: vi.fn((type: string, listener: Listener) => {
      listeners.set(type, listener);
    }),
    emit(type: string) {
      listeners.get(type)?.();
    },
    listeners,
    removeEventListener: vi.fn((type: string, listener: Listener) => {
      if (listeners.get(type) === listener) listeners.delete(type);
    }),
    visibilityState: "visible",
    ...extra,
  };
}

function makeLifecycle(overrides: TestOverrides = {}) {
  resetShellState({ mode: "app" });
  const documentElement = {
    removeAttribute: vi.fn(),
    toggleAttribute: vi.fn(),
  };
  const documentTarget = makeTarget({ documentElement, visibilityState: "visible" });
  const windowTarget = makeTarget();
  const deps = {
    clearLoginTooltip: vi.fn(),
    documentTarget,
    refreshAccountDataOnResume: vi.fn(),
    refreshPendingActivationOnResume: vi.fn(),
    refreshTelegramNotificationsOnResume: vi.fn(),
    windowTarget,
    ...overrides.deps,
  };
  return {
    deps,
    documentElement,
    documentTarget,
    lifecycle: createResumeLifecycle(deps),
    windowTarget,
  };
}

describe("createResumeLifecycle", () => {
  it("clears login tooltip only while login screen is active", () => {
    const { deps, lifecycle } = makeLifecycle();

    lifecycle.onAnyPointerDown();
    shellState.mode = "login";
    lifecycle.onAnyPointerDown();

    expect(deps.clearLoginTooltip).toHaveBeenCalledOnce();
  });

  it("runs resume refreshes when document is visible", () => {
    const { deps, lifecycle } = makeLifecycle();

    lifecycle.onResume();

    expect(deps.refreshPendingActivationOnResume).toHaveBeenCalledOnce();
    expect(deps.refreshTelegramNotificationsOnResume).toHaveBeenCalledOnce();
    expect(deps.refreshAccountDataOnResume).toHaveBeenCalledOnce();
  });

  it("skips resume refreshes while document is hidden", () => {
    const suspendBackgroundWork = vi.fn();
    const { deps, documentElement, documentTarget, lifecycle } = makeLifecycle({
      deps: { suspendBackgroundWork },
    });
    documentTarget.visibilityState = "hidden";

    lifecycle.onResume();
    lifecycle.onVisibilityChange();

    expect(deps.refreshPendingActivationOnResume).not.toHaveBeenCalled();
    expect(deps.refreshTelegramNotificationsOnResume).not.toHaveBeenCalled();
    expect(deps.refreshAccountDataOnResume).not.toHaveBeenCalled();
    expect(suspendBackgroundWork).toHaveBeenCalledOnce();
    expect(documentElement.toggleAttribute).toHaveBeenCalledWith("data-app-backgrounded", true);
  });

  it("re-reads the account payload only once per cooldown", () => {
    let clock = 1_000;
    const { deps, lifecycle } = makeLifecycle({
      deps: { accountRefreshCooldownMs: 15_000, now: () => clock },
    });

    lifecycle.onResume();
    clock += 5_000;
    lifecycle.onResume();
    clock += 15_000;
    lifecycle.onResume();

    expect(deps.refreshAccountDataOnResume).toHaveBeenCalledTimes(2);
    expect(deps.refreshPendingActivationOnResume).toHaveBeenCalledTimes(3);
  });

  it("does not re-read the account payload before sign-in", () => {
    const { deps, lifecycle } = makeLifecycle();
    shellState.mode = "login";

    lifecycle.onResume();

    expect(deps.refreshAccountDataOnResume).not.toHaveBeenCalled();
  });

  it("registers and unregisters browser listeners", () => {
    const { documentElement, documentTarget, lifecycle, windowTarget } = makeLifecycle();

    const cleanup = lifecycle.mount();
    windowTarget.emit("focus");
    cleanup();

    expect(windowTarget.addEventListener).toHaveBeenCalledWith("pointerdown", expect.any(Function));
    expect(windowTarget.addEventListener).toHaveBeenCalledWith("focus", expect.any(Function));
    expect(windowTarget.addEventListener).toHaveBeenCalledWith("pageshow", expect.any(Function));
    expect(documentTarget.addEventListener).toHaveBeenCalledWith(
      "visibilitychange",
      expect.any(Function)
    );
    expect(windowTarget.listeners.size).toBe(0);
    expect(documentTarget.listeners.size).toBe(0);
    expect(documentElement.toggleAttribute).toHaveBeenCalledWith("data-app-backgrounded", false);
    expect(documentElement.removeAttribute).toHaveBeenCalledWith("data-app-backgrounded");
  });
});
