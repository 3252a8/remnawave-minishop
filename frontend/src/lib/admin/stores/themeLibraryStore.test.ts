import { afterEach, describe, expect, it, vi } from "vitest";

import { createThemeLibraryStore } from "./themeLibraryStore.svelte.js";

afterEach(() => {
  vi.useRealTimers();
});

describe("themeLibraryStore", () => {
  it("retains the import failure code and detail after polling", async () => {
    vi.useFakeTimers();
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        operation: {
          id: "import-1",
          state: "validating",
          candidates: [],
          error: "",
          detail: "",
        },
      })
      .mockResolvedValueOnce({
        ok: true,
        operation: {
          id: "import-1",
          state: "failed",
          candidates: [],
          error: "missing_css_file",
          detail: "ocean/style.css",
        },
      });
    const store = createThemeLibraryStore({
      api,
      onChanged: vi.fn(),
      at: (_key, _params, fallback = "") => fallback,
      flash: vi.fn(),
    });

    const inspection = store.inspect({
      url: "https://gitlab.com/example/themes",
      ref: "main",
      subdir: "themes",
    });
    await vi.advanceTimersByTimeAsync(1500);
    await inspection;

    expect(store.failure).toEqual({
      code: "missing_css_file",
      detail: "ocean/style.css",
    });
    expect(store.error).toContain("ocean/style.css");
  });
});
