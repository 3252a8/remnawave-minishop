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

  it("materializes the explicit mode inside the administrator-selected theme family", () => {
    const catalog = {
      default_theme: "dark",
      themes: [
        {
          key: "dark",
          active_variant: "dark",
          tokens: { color_scheme: "dark", bg: "#03070b" },
          variants: {
            dark: { color_scheme: "dark", bg: "#03070b" },
            light: { color_scheme: "light", bg: "#f7f8fb" },
          },
        },
        { key: "ascii", tokens: { color_scheme: "dark", style_preset: "ascii" } },
      ],
    };
    const view = computeThemeView({
      ...BASE,
      cfgThemesCatalog: catalog,
      themePreference: "light",
      systemColorScheme: "dark",
    });
    expect(view.resolvedThemeKey).toBe("dark");
    expect(view.effectiveThemeEntry?.active_variant).toBe("light");
    expect(view.effectiveThemeEntry?.tokens?.bg).toBe("#f7f8fb");
    expect(view.shellToneClass).toBe("theme-light");
  });

  it("never changes the current theme family when the user changes mode", () => {
    const catalog = {
      default_theme: "ascii",
      themes: [
        {
          key: "dark",
          tokens: { color_scheme: "dark" },
          variants: {
            dark: { color_scheme: "dark" },
            light: { color_scheme: "light" },
          },
        },
        {
          key: "ascii",
          tokens: { color_scheme: "dark", style_preset: "ascii" },
          variants: {
            dark: { color_scheme: "dark" },
            light: { color_scheme: "light" },
          },
        },
      ],
    };
    const view = computeThemeView({
      ...BASE,
      cfgThemesCatalog: catalog,
      themePreference: "light",
      systemColorScheme: "dark",
    });
    expect(view.resolvedThemeKey).toBe("ascii");
    expect(view.effectiveThemeEntry?.active_variant).toBe("light");
    expect(view.shellToneClass).toBe("theme-light");
  });

  it("ignores the stored user mode when selection is disabled by the administrator", () => {
    const catalog = {
      default_theme: "dark",
      themes: [
        {
          key: "dark",
          active_variant: "dark",
          tokens: { color_scheme: "dark", bg: "#03070b" },
          variants: {
            dark: { color_scheme: "dark", bg: "#03070b" },
            light: { color_scheme: "light", bg: "#f7f8fb" },
          },
        },
      ],
    };
    const view = computeThemeView({
      ...BASE,
      cfgThemesCatalog: catalog,
      themePreference: "light",
      systemColorScheme: "light",
      userThemeModeEnabled: false,
    });

    expect(view.userThemeModeEnabled).toBe(false);
    expect(view.effectiveThemeEntry?.active_variant).toBe("dark");
    expect(view.shellToneClass).toBe("theme-dark");
  });
});
