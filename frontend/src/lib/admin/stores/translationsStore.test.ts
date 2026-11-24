import { QueryClient } from "@tanstack/svelte-query";
import { describe, expect, it, vi } from "vitest";

import { createTranslationsStore } from "./translationsStore.svelte.js";

describe("translationsStore", () => {
  it("reuses the translations index and refreshes it explicitly", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      languages: [{ code: "en", label: "English", flag: "🇬🇧", base: true }],
      groups: [],
      path: "locales-overrides.json",
      override_count: 0,
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const store = createTranslationsStore({
      api: api as never,
      at: (_key, _params, fallback) => fallback || "",
      onToast: vi.fn(),
      queryClient,
    });

    await store.loadTranslations();
    await store.loadTranslations();
    expect(api).toHaveBeenCalledTimes(1);
    expect(api.mock.calls[0][0]).toBe("/admin/translations?view=index");

    await store.loadTranslations({ refresh: true });
    expect(api).toHaveBeenCalledTimes(2);
    queryClient.clear();
  });
  it("hydrates a single group once, then searches all groups without losing local edits", async () => {
    const info = {
      id: "p:a",
      title: "Plugin",
      counts: { user: { keys: 1, overrides: 0 } },
      items: [],
    };
    const other = { ...info, id: "core" };
    const loaded = {
      id: info.id,
      title: info.title,
      items: [{ key: "x", values: { en: { base: "a" } } }],
    };
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        languages: [{ code: "en", label: "English" }],
        groups: [info, other],
      })
      .mockResolvedValueOnce({ ok: true, groups: [loaded] })
      .mockResolvedValueOnce({ ok: true, groups: [loaded, { ...loaded, id: other.id }] });
    const store = createTranslationsStore({
      api: api as never,
      at: (_k, _p, v) => v || "",
      onToast: vi.fn(),
    });
    await store.loadTranslations();
    await Promise.all([store.loadTranslationItems(info.id), store.loadTranslationItems(info.id)]);
    expect(api.mock.calls.map(([path]) => path)).toEqual([
      "/admin/translations?view=index",
      "/admin/translations?group_id=p%3Aa",
    ]);
    expect(store.translationGroups).toEqual([loaded, other]);
    store.addTranslationLanguage("de");
    store.markDirty("de", "x", "neu");
    await store.loadTranslationItems();
    await store.loadTranslationItems(info.id);
    expect(api).toHaveBeenCalledTimes(3);
    expect(store.translationGroups.every((g) => g.items?.length === 1)).toBe(true);
    expect(store.translationLanguages.map((l) => l.code)).toContain("de");
    expect(store.translationsDirty["de:x"].value).toBe("neu");
  });
});
