import { describe, expect, it, vi } from "vitest";

import { createAppLaunchActions } from "./appLaunchActions.js";

function makeActions(overrides = {}) {
  const state = { target: "" };
  const deps = {
    openTarget: vi.fn(),
    readTarget: vi.fn(() => "https://example.test/app"),
    setAppLaunchTarget: vi.fn((target) => {
      state.target = target;
    }),
    ...overrides.deps,
  };
  return { actions: createAppLaunchActions(deps), deps, state };
}

describe("createAppLaunchActions", () => {
  it("refreshes the launch target from the current location", () => {
    const { actions, deps, state } = makeActions();

    expect(actions.refreshAppLaunchTarget()).toBe("https://example.test/app");

    expect(state.target).toBe("https://example.test/app");
    expect(deps.setAppLaunchTarget).toHaveBeenCalledWith("https://example.test/app");
  });

  it("opens an explicit target after trimming it", () => {
    const { actions, deps, state } = makeActions();

    expect(actions.openAppLaunchTarget("  tg://resolve?domain=bot  ")).toBe(true);

    expect(state.target).toBe("tg://resolve?domain=bot");
    expect(deps.readTarget).not.toHaveBeenCalled();
    expect(deps.openTarget).toHaveBeenCalledWith("tg://resolve?domain=bot");
  });

  it("refreshes before opening when no explicit target is supplied", () => {
    const { actions, deps, state } = makeActions();

    expect(actions.openAppLaunchTarget()).toBe(true);

    expect(state.target).toBe("https://example.test/app");
    expect(deps.readTarget).toHaveBeenCalledOnce();
    expect(deps.openTarget).toHaveBeenCalledWith("https://example.test/app");
  });

  it("does not open an empty target", () => {
    const { actions, deps, state } = makeActions({
      deps: { readTarget: vi.fn(() => "") },
    });

    expect(actions.openAppLaunchTarget()).toBe(false);

    expect(state.target).toBe("");
    expect(deps.openTarget).not.toHaveBeenCalled();
  });
});
