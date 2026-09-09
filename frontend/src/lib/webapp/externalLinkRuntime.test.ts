import { describe, expect, it, vi } from "vitest";

import { createExternalLinkRuntime } from "./externalLinkRuntime.js";
import { resetShellState, shellState } from "./shellState.svelte";
type TestOverrides = Record<string, unknown>;

function makeRuntime(overrides: TestOverrides = {}) {
  const state = {
    currentLang: "ru",
    telegram: null,
    ...overrides,
  };
  resetShellState({ tg: state.telegram });
  const deps = {
    assignLocation: vi.fn(),
    getCurrentLang: () => state.currentLang,
    hasTelegramLaunchParams: vi.fn(() => false),
    openHiddenAnchor: vi.fn(),
    openLaunchTarget: vi.fn(),
    refreshTelegram: vi.fn(() => state.telegram),
    readLaunchTarget: vi.fn(() => ""),
  };
  return { deps, runtime: createExternalLinkRuntime(deps), state };
}

describe("createExternalLinkRuntime", () => {
  it("opens Telegram links inside Telegram when available", () => {
    const telegram = { openLink: vi.fn(), openTelegramLink: vi.fn() };
    const { deps, runtime } = makeRuntime({ telegram });

    runtime.openExternalLink("https://t.me/example_support");

    expect(telegram.openTelegramLink).toHaveBeenCalledWith("https://t.me/example_support");
    expect(telegram.openLink).not.toHaveBeenCalled();
    expect(deps.assignLocation).not.toHaveBeenCalled();
  });

  it("falls back to generic Telegram opening when native Telegram opening fails", () => {
    const telegram = {
      openLink: vi.fn(),
      openTelegramLink: vi.fn(() => {
        throw new Error("unavailable");
      }),
    };
    const { deps, runtime } = makeRuntime({ telegram });

    runtime.openExternalLink("https://t.me/example_support");

    expect(telegram.openLink).toHaveBeenCalledWith("https://t.me/example_support", {
      try_instant_view: false,
    });
    expect(deps.assignLocation).not.toHaveBeenCalled();
  });

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
