import { QueryClient } from "@tanstack/svelte-query";
import { describe, expect, it, vi } from "vitest";

import { createTranslationsStore } from "./translationsStore.svelte.js";

describe("translationsStore", () => {
  it("reuses the large translations query and refreshes it explicitly", async () => {
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

    await store.loadTranslations({ refresh: true });
    expect(api).toHaveBeenCalledTimes(2);
    queryClient.clear();
  });
});
