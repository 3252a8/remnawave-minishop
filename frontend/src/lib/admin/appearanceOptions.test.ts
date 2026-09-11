import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import {
  appearanceColorVariables,
  appearanceThemeTokenValue,
  resolveAppearanceColor,
  type ThemeEntry,
} from "./appearanceOptions";

function builtinThemeFile(key: string, filename: "style.css" | "theme.json"): URL {
  return new URL(`../../../../backend/bot/app/web/themes/${key}/${filename}`, import.meta.url);
}

function builtinTheme(key: string): ThemeEntry {
  return JSON.parse(readFileSync(builtinThemeFile(key, "theme.json"), "utf8")) as ThemeEntry;
}

function builtinCssVariables(key: string): Record<string, string> {
  const css = readFileSync(builtinThemeFile(key, "style.css"), "utf8");
  const body = css.match(new RegExp(`\\.theme-key-${key}\\s*\\{([^}]*)\\}`, "s"))?.[1] ?? "";
  return Object.fromEntries(
    [...body.matchAll(/(--[a-z][a-z0-9-]*)\s*:\s*([^;{}]+);/gi)].map((match) => [
      match[1],
      match[2].trim(),
    ])
  );
}

function builtinCssVariablesByVariant(
  key: string,
  variant: "dark" | "light"
): Record<string, string> {
  const css = readFileSync(builtinThemeFile(key, "style.css"), "utf8");
  const base = builtinCssVariables(key);
  const selector = `.theme-key-${key}.theme-variant-${variant}`;
  const body =
    css.match(new RegExp(`${selector.replaceAll(".", "\\.")}\\s*\\{([^}]*)\\}`, "s"))?.[1] ?? "";
  return {
    ...base,
    ...Object.fromEntries(
      [...body.matchAll(/(--[a-z][a-z0-9-]*)\s*:\s*([^;{}]+);/gi)].map((match) => [
        match[1],
        match[2].trim(),
      ])
    ),
  };
}

describe("resolveAppearanceColor", () => {
  it("resolves direct and nested CSS variable references", () => {
    const variables = { "--accent": "#13c07a", "--brand": "var(--accent)" };

    expect(resolveAppearanceColor("var(--accent)", variables)).toBe("#13c07a");
    expect(resolveAppearanceColor("var(--brand)", variables)).toBe("#13c07a");
  });

  it("parses supported direct CSS color syntaxes", () => {
    expect(resolveAppearanceColor("rgb(100% 0% 50% / 25%)", {})).toBe("#ff0080");
    expect(resolveAppearanceColor("hsl(120, 100%, 25%)", {})).toBe("#008000");
    expect(resolveAppearanceColor("hsla(0.5turn 100% 50% / 0.5)", {})).toBe("#00ffff");
    expect(resolveAppearanceColor("transparent", {})).toBe("#000000");
  });

  it("uses a fallback for an unavailable or cyclic CSS variable", () => {
    expect(resolveAppearanceColor("var(--missing, #123456)", {})).toBe("#123456");
    expect(resolveAppearanceColor("var(--a, #654321)", { "--a": "var(--a)" })).toBe("#654321");
  });

  it("resolves straightforward srgb color mixes after variable substitution", () => {
    expect(
      resolveAppearanceColor("color-mix(in srgb, var(--accent) 25%, transparent)", {
        "--accent": "#204060",
      })
    ).toBe("#081018");
  });

  it("does not invent a color for an unresolved expression", () => {
    expect(resolveAppearanceColor("var(--missing)", {})).toBeNull();
    expect(resolveAppearanceColor("var(--a)", { "--a": "var(--b)", "--b": "var(--a)" })).toBeNull();
    expect(resolveAppearanceColor("linear-gradient(red, blue)", {})).toBeNull();
    expect(resolveAppearanceColor("currentColor", {})).toBeNull();
  });

  it("normalizes token names and gives editable tokens priority over CSS defaults", () => {
    const variables = appearanceColorVariables(
      { "--panel-2": "#111111", "--accent": "#222222" },
      { panel_2: "#abcdef", accent: "#123456" }
    );

    expect(resolveAppearanceColor("var(--panel-2)", variables)).toBe("#abcdef");
    expect(resolveAppearanceColor("var(--accent)", variables)).toBe("#123456");
  });
});

describe("built-in appearance themes", () => {
  it("keeps every built-in descriptor available as test data", () => {
    expect(["dark", "light", "ascii", "windows95"].map((key) => builtinTheme(key).key)).toEqual([
      "dark",
      "light",
      "ascii",
      "windows95",
    ]);
  });

  it("resolves the built-in default dark and light palettes", () => {
    const theme = builtinTheme("dark");
    const darkTokens = { ...theme.tokens, ...theme.variants?.dark };
    const lightTokens = { ...theme.tokens, ...theme.variants?.light };

    expect(
      resolveAppearanceColor(appearanceThemeTokenValue(theme, darkTokens, "bg"), darkTokens)
    ).toBe("#03070b");
    expect(
      resolveAppearanceColor(appearanceThemeTokenValue(theme, lightTokens, "panel"), lightTokens)
    ).toBe("#ffffff");
  });

  it("resolves package CSS colors while preserving their raw expressions", () => {
    const theme = {
      ...builtinTheme("ascii"),
      css_variables: builtinCssVariables("ascii"),
      css_variables_by_variant: {
        dark: builtinCssVariablesByVariant("ascii", "dark"),
        light: builtinCssVariablesByVariant("ascii", "light"),
      },
    };
    const tokens = { ...theme.tokens, ...theme.variants?.dark };
    const rawNav = appearanceThemeTokenValue(theme, tokens, "nav_bg");
    const variables = appearanceColorVariables(theme.css_variables ?? {}, tokens);

    expect(rawNav).toBe("var(--ascii-bg)");
    expect(resolveAppearanceColor(rawNav, variables)).toBe("#000000");
    expect(appearanceThemeTokenValue(theme, tokens, "bg")).toBe("var(--ascii-bg)");
  });

  it("uses the selected ASCII variant when resolving nested package CSS variables", () => {
    const theme = {
      ...builtinTheme("ascii"),
      css_variables_by_variant: {
        dark: builtinCssVariablesByVariant("ascii", "dark"),
        light: builtinCssVariablesByVariant("ascii", "light"),
      },
    };
    const lightVariables = theme.css_variables_by_variant.light;
    const lightTokens = { ...theme.tokens, ...theme.variants?.light };
    const rawNav = appearanceThemeTokenValue(theme, lightTokens, "nav_bg", lightVariables);

    expect(rawNav).toBe("var(--ascii-bg)");
    expect(
      resolveAppearanceColor(rawNav, appearanceColorVariables(lightVariables, lightTokens))
    ).toBe("#ffffff");
  });

  it("uses editable tokens ahead of package CSS defaults", () => {
    const theme = { ...builtinTheme("windows95"), css_variables: builtinCssVariables("windows95") };
    const tokens = { ...theme.tokens, ...theme.variants?.light, nav_bg: "#123456" };
    const rawNav = appearanceThemeTokenValue(theme, tokens, "nav_bg");

    expect(rawNav).toBe("#123456");
    expect(
      resolveAppearanceColor(rawNav, appearanceColorVariables(theme.css_variables ?? {}, tokens))
    ).toBe("#123456");
  });
});
