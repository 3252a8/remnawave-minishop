import { describe, expect, it, vi } from "vitest";

import { createExternalLinkRuntime } from "./externalLinkRuntime.js";
import { resetShellState, shellState } from "./shellState.svelte.ts";

function makeRuntime(overrides = {}) {
  const state = {
    currentLang: "ru",
    telegram: null,
    ...overrides,
  };
  resetShellState();
  const deps = {
    assignLocation: vi.fn(),
    getCurrentLang: () => state.currentLang,
    getTelegram: () => state.telegram,
    hasTelegramLaunchParams: vi.fn(() => false),
    openHiddenAnchor: vi.fn(),
    openLaunchTarget: vi.fn(),
    refreshTelegram: vi.fn(() => state.telegram),
    readLaunchTarget: vi.fn(() => ""),
    setTelegram: vi.fn((value) => {
      state.telegram = value;
    }),
  };
  return { deps, runtime: createExternalLinkRuntime(deps), state };
}

describe("createExternalLinkRuntime", () => {
  it("opens external links through Telegram when available", () => {
    const telegram = { openLink: vi.fn() };
    const { deps, runtime } = makeRuntime({ telegram });

    runtime.openExternalLink("https://example.test/page");

    expect(telegram.openLink).toHaveBeenCalledWith("https://example.test/page", {
      try_instant_view: false,
    });
    expect(deps.assignLocation).not.toHaveBeenCalled();
  });

  it("falls back to browser navigation for external links", () => {
    const { deps, runtime } = makeRuntime();

    runtime.openExternalLink("https://example.test/page");

    expect(deps.assignLocation).toHaveBeenCalledWith("https://example.test/page");
  });

  it("delegates app links to the app link opener", () => {
    const { deps, runtime } = makeRuntime();

    runtime.openAppLink("vless://profile");

    expect(deps.openHiddenAnchor).toHaveBeenCalledWith("vless://profile");
  });

  it("keeps app launch target actions wired to shell state", () => {
    const { deps, runtime } = makeRuntime();

    expect(runtime.openAppLaunchTarget("tg://resolve?domain=bot")).toBe(true);

    expect(shellState.appLaunchTarget).toBe("tg://resolve?domain=bot");
    expect(deps.openLaunchTarget).toHaveBeenCalledWith("tg://resolve?domain=bot");
  });
});
