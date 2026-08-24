import { describe, expect, it } from "vitest";

import {
  activeThemeOption,
  normalizeThemePreference,
  resolveThemePreference,
  resolveThemePreferenceKey,
  themeOptions,
  themeSwitcherAvailable,
  THEME_PREFERENCE_AUTO,
} from "./themePreference.js";

const STOCK_CATALOG = {
  default_theme: "windows95",
  themes: [
    {
      key: "dark",
      tokens: { color_scheme: "dark" },
      variants: {
        dark: { color_scheme: "dark", bg: "#03070b" },
        light: { color_scheme: "light", bg: "#f7f8fb" },
      },
    },
    {
      key: "windows95",
      active_variant: "light",
      tokens: { color_scheme: "light", style_preset: "win95" },
      variants: {
        light: { color_scheme: "light" },
        dark: { color_scheme: "dark" },
      },
    },
    {
      key: "ascii",
      tokens: { color_scheme: "dark", style_preset: "ascii" },
      variants: {
        light: { color_scheme: "light" },
        dark: { color_scheme: "dark" },
      },
    },
  ],
};

describe("normalizeThemePreference", () => {
  it("accepts only auto, light, and dark", () => {
    expect(normalizeThemePreference("AUTO")).toBe(THEME_PREFERENCE_AUTO);
    expect(normalizeThemePreference(" Light ")).toBe("light");
    expect(normalizeThemePreference("DARK")).toBe("dark");
  });

  it("collapses old theme keys and unusable values to auto", () => {
    expect(normalizeThemePreference("windows95")).toBe(THEME_PREFERENCE_AUTO);
    expect(normalizeThemePreference("aurora-dark")).toBe(THEME_PREFERENCE_AUTO);
    expect(normalizeThemePreference(null)).toBe(THEME_PREFERENCE_AUTO);
  });
});

describe("themeSwitcherAvailable", () => {
  it("requires both variants on the administrator-selected theme", () => {
    expect(themeSwitcherAvailable(STOCK_CATALOG)).toBe(true);
    expect(
      themeSwitcherAvailable({
        default_theme: "ascii",
        themes: [{ key: "ascii", variants: { dark: { color_scheme: "dark" } } }],
      })
    ).toBe(false);
  });

  it("does not become available merely because another theme has both variants", () => {
    expect(
      themeSwitcherAvailable({
        default_theme: "custom",
        themes: [{ key: "custom", tokens: { color_scheme: "dark" } }, STOCK_CATALOG.themes[0]],
      })
    ).toBe(false);
  });
});

describe("themeOptions", () => {
  it("contains modes instead of catalog theme families", () => {
    expect(themeOptions("Авто", "Светлый", "Тёмный")).toEqual([
      { value: "auto", label: "Авто" },
      { value: "light", label: "Светлый" },
      { value: "dark", label: "Тёмный" },
    ]);
  });
});

describe("activeThemeOption", () => {
  it("normalizes the stored mode for the select", () => {
    expect(activeThemeOption("LIGHT")).toBe("light");
    expect(activeThemeOption("ascii")).toBe("auto");
  });
});

describe("resolveThemePreference", () => {
  it("forces light mode within the current Windows 95 theme", () => {
    expect(
      resolveThemePreference({
        catalog: STOCK_CATALOG,
        preference: "light",
        systemScheme: "dark",
      })
    ).toEqual({ key: "windows95", variant: "light" });
  });

  it("forces dark mode within the current Windows 95 theme", () => {
    expect(
      resolveThemePreference({
        catalog: STOCK_CATALOG,
        preference: "dark",
        systemScheme: "light",
      })
    ).toEqual({ key: "windows95", variant: "dark" });
  });

  it("follows the client mode in auto without switching theme families", () => {
    expect(
      resolveThemePreference({
        catalog: STOCK_CATALOG,
        preference: "auto",
        systemScheme: "dark",
      })
    ).toEqual({ key: "windows95", variant: "dark" });
  });

  it("leaves the administrator's active variant untouched without a client signal", () => {
    expect(
      resolveThemePreference({
        catalog: STOCK_CATALOG,
        preference: "auto",
        systemScheme: "",
      })
    ).toEqual({ key: "", variant: "" });
  });

  it("does not override a current theme that lacks one of the modes", () => {
    const catalog = {
      default_theme: "custom",
      themes: [{ key: "custom", variants: { dark: { color_scheme: "dark" } } }],
    };
    expect(resolveThemePreference({ catalog, preference: "light", systemScheme: "dark" })).toEqual({
      key: "",
      variant: "",
    });
    expect(resolveThemePreferenceKey({ catalog, preference: "dark", systemScheme: "light" })).toBe(
      ""
    );
  });
});
