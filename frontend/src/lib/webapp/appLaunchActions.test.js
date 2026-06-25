import { describe, expect, it, vi } from "vitest";

import { createAppLaunchActions } from "./appLaunchActions.js";
import { resetShellState, shellState } from "./shellState.svelte.ts";

function makeActions(overrides = {}) {
  resetShellState();
  const deps = {
    openTarget: vi.fn(),
    readTarget: vi.fn(() => "https://example.test/app"),
    ...overrides.deps,
  };
  return { actions: createAppLaunchActions(deps), deps };
}

describe("createAppLaunchActions", () => {
  it("refreshes the launch target from the current location", () => {
    const { actions } = makeActions();

    expect(actions.refreshAppLaunchTarget()).toBe("https://example.test/app");

    expect(shellState.appLaunchTarget).toBe("https://example.test/app");
  });

  it("opens an explicit target after trimming it", () => {
    const { actions, deps } = makeActions();

    expect(actions.openAppLaunchTarget("  tg://resolve?domain=bot  ")).toBe(true);

    expect(shellState.appLaunchTarget).toBe("tg://resolve?domain=bot");
    expect(deps.readTarget).not.toHaveBeenCalled();
    expect(deps.openTarget).toHaveBeenCalledWith("tg://resolve?domain=bot");
  });

  it("refreshes before opening when no explicit target is supplied", () => {
    const { actions, deps } = makeActions();

    expect(actions.openAppLaunchTarget()).toBe(true);

    expect(shellState.appLaunchTarget).toBe("https://example.test/app");
    expect(deps.readTarget).toHaveBeenCalledOnce();
    expect(deps.openTarget).toHaveBeenCalledWith("https://example.test/app");
  });

  it("does not open an empty target", () => {
    const { actions, deps } = makeActions({
      deps: { readTarget: vi.fn(() => "") },
    });

    expect(actions.openAppLaunchTarget()).toBe(false);

    expect(shellState.appLaunchTarget).toBe("");
    expect(deps.openTarget).not.toHaveBeenCalled();
  });
});
