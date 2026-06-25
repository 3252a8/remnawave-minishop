import { describe, expect, it, vi } from "vitest";

import { createConnectActions } from "./connectActions.js";

function makeActions(overrides = {}) {
  const state = {
    publicInstallSubscription: { connect_url: "https://example.test/public" },
    subscription: { connect_url: "https://example.test/subscription" },
    trialActivationResult: { connect_url: "https://example.test/trial" },
    ...overrides.state,
  };
  const deps = {
    getPublicInstallSubscription: () => state.publicInstallSubscription,
    getSubscription: () => state.subscription,
    getTrialActivationResult: () => state.trialActivationResult,
    openExternalLink: vi.fn(),
    showToast: vi.fn(),
    t: vi.fn((key) => key),
    ...overrides.deps,
  };
  return { actions: createConnectActions(deps), deps, state };
}

describe("createConnectActions", () => {
  it("opens resolved connect links and reports unavailable links", () => {
    const { actions, deps } = makeActions();

    expect(actions.openResolvedConnectLink("https://example.test/config")).toBe(true);
    expect(actions.openResolvedConnectLink("")).toBe(false);

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://example.test/config");
    expect(deps.showToast).toHaveBeenCalledWith("wa_connect_link_unavailable");
  });

  it("opens the current subscription link", () => {
    const { actions, deps } = makeActions();

    expect(actions.openConnectLink()).toBe(true);

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://example.test/subscription");
  });

  it("opens public install links from the public subscription", () => {
    const { actions, deps } = makeActions();

    expect(actions.openPublicConnectLink()).toBe(true);

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://example.test/public");
  });

  it("prefers trial links for trial connect actions", () => {
    const { actions, deps } = makeActions();

    expect(actions.openTrialConnectLink()).toBe(true);

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://example.test/trial");
  });

  it("prefers active subscription links for activation dialogs", () => {
    const { actions, deps } = makeActions();

    expect(actions.openActivationConnectLink()).toBe(true);

    expect(deps.openExternalLink).toHaveBeenCalledWith("https://example.test/subscription");
  });
});
