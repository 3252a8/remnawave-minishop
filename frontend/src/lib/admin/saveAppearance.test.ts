import { describe, expect, it, vi } from "vitest";
import { saveAppearanceChanges } from "./saveAppearance";
import { createThemesStore } from "./stores/themesStore.svelte";

describe("saving appearance", () => {
  it("persists the theme draft before a settings refresh reloads the catalog", async () => {
    let catalog = {
      default_theme: "dark",
      themes: [{ key: "dark", tokens: {}, variants: { light: { radius: "8px" } } }],
    };
    const api = vi.fn();
    api.mockImplementation(async (_path: string, options?: RequestInit) => {
      if (typeof options?.body === "string") catalog = JSON.parse(options.body).catalog;
      return { ok: true, generation: 1, catalog };
    });
    const themesStore = createThemesStore({ api, flash: vi.fn(), at: (key) => key });
    await themesStore.loadThemes();
    themesStore.setThemeToken("dark", "radius", "20px", { variant: "light" });
    const onSettingsSaved = vi.fn(async () => themesStore.loadThemes());
    const settingsStore = {
      saveSettings: vi.fn(
        async (onSaved?: Parameters<typeof saveAppearanceChanges>[0]["onSettingsSaved"]) => {
          await onSaved?.({ updates: { WEBAPP_COMPACT_HOME_ENABLED: true }, deletes: [] });
          return true;
        }
      ),
    };

    await expect(
      saveAppearanceChanges({
        settingsStore,
        themesStore,
        dirtyKeys: ["WEBAPP_COMPACT_HOME_ENABLED"],
        onSettingsSaved,
      })
    ).resolves.toBe(true);
    expect(catalog.themes[0].variants.light.radius).toBe("20px");
    expect(onSettingsSaved).toHaveBeenCalledOnce();
  });

  it("keeps unsaved theme edits available when settings persistence fails", async () => {
    const themesStore = { saveThemes: vi.fn().mockResolvedValue(true) };
    const onSettingsSaved = vi.fn();
    await expect(
      saveAppearanceChanges({
        settingsStore: { saveSettings: vi.fn().mockResolvedValue(false) },
        themesStore,
        dirtyKeys: ["WEBAPP_LOGO_URL"],
        onSettingsSaved,
      })
    ).resolves.toBe(false);
    expect(themesStore.saveThemes).not.toHaveBeenCalled();
    expect(onSettingsSaved).not.toHaveBeenCalled();
  });
});
