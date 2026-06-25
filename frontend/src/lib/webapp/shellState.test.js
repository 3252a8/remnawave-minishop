import { describe, expect, it } from "vitest";

import {
  createInitialShellState,
  createShellState,
  resetShellState,
  shellState,
} from "./shellState.svelte.ts";

describe("shellState", () => {
  it("creates the default webapp shell state", () => {
    expect(createInitialShellState()).toMatchObject({
      activeTab: "home",
      adminActiveSection: "stats",
      appActions: null,
      csrfToken: "",
      data: null,
      mode: "loading",
      screen: "home",
      telegramSdkStatus: "idle",
      token: "",
    });
  });

  it("applies initialization overrides to fresh shell state instances", () => {
    const state = createShellState({
      activeTab: "settings",
      data: { user: { is_admin: true } },
      mode: "app",
      screen: "admin",
      token: "local-preview",
    });

    expect(state).toMatchObject({
      activeTab: "settings",
      data: { user: { is_admin: true } },
      mode: "app",
      screen: "admin",
      token: "local-preview",
    });
  });

  it("resets the shared shell state in place", () => {
    shellState.mode = "app";
    shellState.screen = "support";

    const reset = resetShellState({ csrfToken: "csrf" });

    expect(reset).toBe(shellState);
    expect(shellState).toMatchObject({
      csrfToken: "csrf",
      mode: "loading",
      screen: "home",
    });
  });
});
