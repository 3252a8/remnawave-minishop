import { describe, expect, it, vi } from "vitest";

import { createResumeLifecycle } from "./resumeLifecycle.js";
import { resetShellState, shellState } from "./shellState.svelte.ts";

function makeTarget(extra = {}) {
  const listeners = new Map();
  return {
    addEventListener: vi.fn((type, listener) => {
      listeners.set(type, listener);
    }),
    emit(type) {
      listeners.get(type)?.();
    },
    listeners,
    removeEventListener: vi.fn((type, listener) => {
      if (listeners.get(type) === listener) listeners.delete(type);
    }),
    ...extra,
  };
}

function makeLifecycle(overrides = {}) {
  resetShellState({ mode: "app" });
  const documentTarget = makeTarget({ visibilityState: "visible" });
  const windowTarget = makeTarget();
  const deps = {
    clearLoginTooltip: vi.fn(),
    documentTarget,
    refreshPendingActivationOnResume: vi.fn(),
    refreshTelegramNotificationsOnResume: vi.fn(),
    windowTarget,
    ...overrides.deps,
  };
  return {
    deps,
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
  });

  it("skips resume refreshes while document is hidden", () => {
    const { deps, documentTarget, lifecycle } = makeLifecycle();
    documentTarget.visibilityState = "hidden";

    lifecycle.onResume();
    lifecycle.onVisibilityChange();

    expect(deps.refreshPendingActivationOnResume).not.toHaveBeenCalled();
    expect(deps.refreshTelegramNotificationsOnResume).not.toHaveBeenCalled();
  });

  it("registers and unregisters browser listeners", () => {
    const { documentTarget, lifecycle, windowTarget } = makeLifecycle();

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
  });
});
