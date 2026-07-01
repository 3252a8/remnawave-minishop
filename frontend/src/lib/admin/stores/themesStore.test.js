import { describe, expect, it, vi } from "vitest";

import { createThemesStore } from "./themesStore.svelte.ts";

function makeStore(api = vi.fn()) {
  const store = createThemesStore({
    api,
    flash: vi.fn(),
    at: (key) => key,
  });
  return { api, store };
}

describe("themesStore", () => {
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
});
