import { describe, expect, it } from "vitest";

import { computeThemeView } from "./themeView.js";

const CATALOG = {
  default_theme: "ocean",
  themes: [
    { key: "ocean", tokens: { color_scheme: "light" }, use_in_admin: false },
    {
      key: "dark",
      active_variant: "light",
      tokens: { color_scheme: "light", bg: "#fff" },
      variants: {
        dark: { color_scheme: "dark", bg: "#03070b" },
        light: { color_scheme: "light", bg: "#fff" },
      },
    },
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

  it("uses the dark system variant of the default theme in admin when the active theme opts out", () => {
    const view = computeThemeView({
      ...BASE,
      screen: "admin",
      themePreference: "auto",
      systemColorScheme: "dark",
    });
    expect(view.effectiveThemeEntry?.key).toBe("dark");
    expect(view.effectiveThemeEntry?.active_variant).toBe("dark");
    expect(view.effectiveThemeEntry?.tokens?.bg).toBe("#03070b");
    expect(view.shellToneClass).toBe("theme-dark");
    expect(view.shellThemeClass).toContain("theme-variant-dark");
    expect(view.toastTheme).toBe("dark");
  });

  it("uses the light system variant of the default theme in admin when the active theme opts out", () => {
    const view = computeThemeView({
      ...BASE,
      screen: "admin",
      themePreference: "auto",
      systemColorScheme: "light",
    });
    expect(view.effectiveThemeEntry?.key).toBe("dark");
    expect(view.effectiveThemeEntry?.active_variant).toBe("light");
    expect(view.effectiveThemeEntry?.tokens?.bg).toBe("#fff");
    expect(view.shellToneClass).toBe("theme-light");
    expect(view.shellThemeClass).toContain("theme-variant-light");
    expect(view.toastTheme).toBe("light");
  });

  it("keeps the active custom theme outside admin", () => {
    const view = computeThemeView({
      ...BASE,
      themePreference: "auto",
      systemColorScheme: "dark",
    });
    expect(view.resolvedThemeKey).toBe("ocean");
    expect(view.effectiveThemeEntry?.key).toBe("ocean");
    expect(view.shellToneClass).toBe("theme-light");
  });

  it("keeps an admin-enabled active custom theme in admin", () => {
    const catalog = {
      ...CATALOG,
      themes: CATALOG.themes.map((theme) =>
        theme.key === "ocean" ? { ...theme, use_in_admin: true } : theme
      ),
    };
    const view = computeThemeView({
      ...BASE,
      cfgThemesCatalog: catalog,
      screen: "admin",
      themePreference: "auto",
      systemColorScheme: "dark",
    });
    expect(view.resolvedThemeKey).toBe("ocean");
    expect(view.effectiveThemeEntry?.key).toBe("ocean");
    expect(view.shellToneClass).toBe("theme-light");
  });

  it("keeps a fallback accent and serializes transparency for CSS-backed themes", () => {
    const view = computeThemeView({
      ...BASE,
      primaryColor: "#39bce0",
      cfgThemesCatalog: {
        default_theme: "liquid-glass",
        themes: [
          {
            key: "liquid-glass",
            css_file: "theme.css",
            tokens: { color_scheme: "dark", transparency: 46 },
          },
        ],
      },
    });

    expect(view.shellStyle).toContain("--accent:#39bce0");
    expect(view.shellStyle).toContain("--theme-transparency:0.46");
  });

  it("honours an allowed preview theme key", () => {
    const view = computeThemeView({ ...BASE, themePreviewKey: "dark" });
    expect(view.resolvedThemeKey).toBe("dark");
    expect(view.effectiveThemeEntry?.key).toBe("dark");
  });

  it("exposes the referral bonus list mode of the effective theme", () => {
    const view = computeThemeView({
      ...BASE,
      cfgThemesCatalog: {
        default_theme: "ocean",
        themes: [
          {
            key: "ocean",
            tokens: { color_scheme: "dark", referral_bonus_list: "expanded" },
          },
        ],
      },
    });

    expect(view.referralBonusListMode).toBe("expanded");
    expect(computeThemeView(BASE).referralBonusListMode).toBe("plain");
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
