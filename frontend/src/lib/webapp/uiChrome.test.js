import { afterEach, describe, expect, it, vi } from "vitest";

import { createUiChrome } from "./uiChrome.js";
import { resetShellState, shellState } from "./shellState.svelte.ts";

function installWindowTimers() {
  vi.stubGlobal("window", {
    clearTimeout,
    setTimeout,
  });
}

function makeChrome(overrides = {}) {
  const state = {
    currentLang: "ru",
  };
  resetShellState();
  const deps = {
    getCurrentLang: () => state.currentLang,
    normalizeLangCode: (value) =>
      String(value || "")
        .trim()
        .toLowerCase(),
    ...overrides.deps,
  };
  return { actions: createUiChrome(deps), deps, state };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("createUiChrome", () => {
  it("locks and unlocks body scrolling when a modal is active", () => {
    const body = { style: { overflow: "" } };
    vi.stubGlobal("document", { body });
    const { actions } = makeChrome();

    actions.syncBodyScrollLock(true);

    expect(body.style.overflow).toBe("hidden");

    actions.syncBodyScrollLock(false);

    expect(body.style.overflow).toBe("");
  });

  it("arms and clears the language click guard around menu transitions", () => {
    vi.useFakeTimers();
    installWindowTimers();
    const { actions } = makeChrome();

    actions.setLanguageMenuOpen(true);

    expect(shellState.languageMenuOpen).toBe(true);
    expect(shellState.languageClickGuard).toBe(true);
    expect(shellState.languageClickGuardArmed).toBe(false);

    vi.advanceTimersByTime(220);

    expect(shellState.languageClickGuardArmed).toBe(true);

    actions.setLanguageMenuOpen(false);

    expect(shellState.languageMenuOpen).toBe(false);
    expect(shellState.languageClickGuard).toBe(true);
    expect(shellState.languageClickGuardArmed).toBe(false);

    vi.advanceTimersByTime(260);

    expect(shellState.languageClickGuard).toBe(false);
  });

  it("normalizes and applies a changed guest language", () => {
    vi.useFakeTimers();
    installWindowTimers();
    const { actions, state } = makeChrome();

    actions.updateGuestLanguage(" EN ");

    expect(shellState.guestLanguage).toBe("en");

    state.currentLang = "en";
    actions.updateGuestLanguage("en");

    expect(shellState.guestLanguage).toBe("en");
  });
});
