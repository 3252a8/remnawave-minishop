import { describe, expect, it } from "vitest";

import { computeThemeView } from "./themeView.js";

const CATALOG = {
  default_theme: "ocean",
  themes: [
    { key: "ocean", tokens: { color_scheme: "light" }, use_in_admin: false },
    { key: "dark", tokens: { color_scheme: "dark" } },
  ],
};

const BASE = {
  themePreviewDraft: null,
  themePreviewKey: null,
  data: null,
  user: {},
  screen: "app",
  cfgThemesCatalog: CATALOG,
  primaryColor: undefined,
};

describe("computeThemeView", () => {
  it("uses the catalog default theme on app screens", () => {
    const view = computeThemeView(BASE);
    expect(view.resolvedThemeKey).toBe("ocean");
    expect(view.effectiveThemeEntry?.key).toBe("ocean");
    expect(view.shellToneClass).toBe("theme-light");
    expect(view.toastTheme).toBe("light");
  });

  it("falls back to dark in admin when the active theme opts out of admin", () => {
    const view = computeThemeView({ ...BASE, screen: "admin" });
    expect(view.effectiveThemeEntry?.key).toBe("dark");
    expect(view.shellToneClass).toBe("theme-dark");
    expect(view.toastTheme).toBe("dark");
  });

  it("honours an allowed preview theme key", () => {
    const view = computeThemeView({ ...BASE, themePreviewKey: "dark" });
    expect(view.resolvedThemeKey).toBe("dark");
    expect(view.effectiveThemeEntry?.key).toBe("dark");
  });

  it("ignores a preview key for non-admin users with a server account", () => {
    const view = computeThemeView({
      ...BASE,
      themePreviewKey: "dark",
      data: { user: { is_admin: false } },
      user: { is_admin: false },
    });
    expect(view.resolvedThemeKey).toBe("ocean");
  });
});
