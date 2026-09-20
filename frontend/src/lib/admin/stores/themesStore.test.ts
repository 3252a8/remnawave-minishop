import { describe, expect, it, vi } from "vitest";

import { createThemesStore } from "./themesStore.svelte";

function makeStore(api = vi.fn()) {
  const store = createThemesStore({
    api,
    flash: vi.fn(),
    at: (key: string) => key,
  });
  return { api, store };
}

describe("themesStore", () => {
  it("stays clean after loading an untouched catalog, becomes dirty after an edit, and clears after save", async () => {
    const catalog = {
      default_theme: "ascii",
      themes: [
        {
          key: "ascii",
          active_variant: "dark",
          tokens: { color_scheme: "dark", style_preset: "ascii" },
          variants: { dark: { color_scheme: "dark" }, light: { color_scheme: "light" } },
          css_variables: { "--ascii-bg": "#000000", "--nav-bg": "var(--ascii-bg)" },
        },
      ],
    };
    const api = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, generation: 1, catalog })
      .mockResolvedValueOnce({
        ok: true,
        generation: 2,
        catalog: {
          ...catalog,
          themes: [
            {
              ...catalog.themes[0],
              variants: {
                ...catalog.themes[0].variants,
                dark: { color_scheme: "dark", bg: "#101010" },
              },
            },
          ],
        },
      });
    const { store } = makeStore(api);

    await store.loadThemes();

    expect(store.themesDirty).toBe(false);
    expect(store.themesCatalog).toEqual(store.savedThemesCatalog);

    store.setThemeToken("ascii", "bg", "#101010", { variant: "dark" });
    expect(store.themesDirty).toBe(true);

    await expect(store.saveThemes()).resolves.toBe(true);
    expect(store.themesDirty).toBe(false);
    expect(store.themesCatalog).toEqual(store.savedThemesCatalog);
  });

  it("persists the explicitly activated theme", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      generation: 2,
      catalog: {
        default_theme: "ocean",
        themes: [
          { key: "dark", tokens: { color_scheme: "dark" } },
          { key: "ocean", tokens: { color_scheme: "light" } },
        ],
      },
    });
    const { store } = makeStore(api);
    store.themesCatalog = {
      default_theme: "dark",
      themes: [
        { key: "dark", tokens: { color_scheme: "dark" } },
        { key: "ocean", tokens: { color_scheme: "light" } },
      ],
    };
    store.savedThemesCatalog = structuredClone(store.themesCatalog);

    store.setCurrentTheme("ocean");

    await expect(store.saveThemes()).resolves.toBe(true);
    expect(JSON.parse(api.mock.calls[0][1].body)).toMatchObject({
      catalog: { default_theme: "ocean" },
    });
    expect(store.savedThemesCatalog.default_theme).toBe("ocean");
  });

  it("surfaces whether uploaded appearance assets were persisted", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      logo_url: "/webapp-uploaded-logo/logo.png",
      favicon_url: "/webapp-favicon/logo/icon-180.png",
      persisted: false,
    });
    const { store } = makeStore(api);

    const result = await store.uploadLogoUrl("https://example.com/logo.png");

    expect(api).toHaveBeenCalledWith("/admin/appearance/logo", {
      method: "POST",
      body: JSON.stringify({ url: "https://example.com/logo.png" }),
    });
    expect(result).toEqual({
      logoUrl: "/webapp-uploaded-logo/logo.png",
      faviconUrl: "/webapp-favicon/logo/icon-180.png",
      persisted: false,
    });
  });

  it("returns favicon upload persistence state", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      favicon_url: "/webapp-favicon/custom/icon-180.png",
      persisted: true,
    });
    const { store } = makeStore(api);

    const result = await store.uploadFaviconUrl("https://example.com/icon.png");

    expect(api).toHaveBeenCalledWith("/admin/appearance/favicon", {
      method: "POST",
      body: JSON.stringify({ url: "https://example.com/icon.png" }),
    });
    expect(result).toEqual({
      faviconUrl: "/webapp-favicon/custom/icon-180.png",
      persisted: true,
    });
  });

  it("uploads a captured preview as multipart data and refreshes the library", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        preview_url: "/webapp-theme-assets/ocean/previews/desktop.webp?v=2",
      })
      .mockResolvedValueOnce({ ok: true, generation: 2, writable: true, installations: [] });
    const { store } = makeStore(api);

    await expect(store.library.uploadPreview("ocean", new Blob(["image"]))).resolves.toContain(
      "/previews/desktop.webp"
    );
    expect(api.mock.calls[0][0]).toBe("/admin/themes/library/ocean/preview");
    expect(api.mock.calls[0][1].body).toBeInstanceOf(FormData);
  });
});
