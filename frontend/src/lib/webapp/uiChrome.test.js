import { afterEach, describe, expect, it, vi } from "vitest";

import { createUiChrome } from "./uiChrome.js";

function installWindowTimers() {
  vi.stubGlobal("window", {
    clearTimeout,
    setTimeout,
  });
}

function makeChrome(overrides = {}) {
  const state = {
    currentLang: "ru",
    guestLanguage: "",
    languageClickGuard: false,
    languageClickGuardArmed: false,
    languageMenuOpen: false,
  };
  const deps = {
    getCurrentLang: () => state.currentLang,
    normalizeLangCode: (value) =>
      String(value || "")
        .trim()
        .toLowerCase(),
    setGuestLanguage: vi.fn((value) => {
      state.guestLanguage = value;
    }),
    setLanguageClickGuard: vi.fn((value) => {
      state.languageClickGuard = value;
    }),
    setLanguageClickGuardArmed: vi.fn((value) => {
      state.languageClickGuardArmed = value;
    }),
    setLanguageMenuOpenState: vi.fn((value) => {
      state.languageMenuOpen = value;
    }),
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
    const { actions, state } = makeChrome();

    actions.setLanguageMenuOpen(true);

    expect(state.languageMenuOpen).toBe(true);
    expect(state.languageClickGuard).toBe(true);
    expect(state.languageClickGuardArmed).toBe(false);

    vi.advanceTimersByTime(220);

    expect(state.languageClickGuardArmed).toBe(true);

    actions.setLanguageMenuOpen(false);

    expect(state.languageMenuOpen).toBe(false);
    expect(state.languageClickGuard).toBe(true);
    expect(state.languageClickGuardArmed).toBe(false);

    vi.advanceTimersByTime(260);

    expect(state.languageClickGuard).toBe(false);
  });

  it("normalizes and applies a changed guest language", () => {
    vi.useFakeTimers();
    installWindowTimers();
    const { actions, deps, state } = makeChrome();

    actions.updateGuestLanguage(" EN ");

    expect(state.guestLanguage).toBe("en");
    expect(deps.setGuestLanguage).toHaveBeenCalledWith("en");

    state.currentLang = "en";
    actions.updateGuestLanguage("en");

    expect(deps.setGuestLanguage).toHaveBeenCalledOnce();
  });
});
