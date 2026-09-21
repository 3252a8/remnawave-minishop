import { describe, expect, it, vi } from "vitest";
import { QueryClient } from "@tanstack/svelte-query";

import { createSettingsStore } from "./settingsStore.svelte.js";

describe("settingsStore", () => {
  it("reuses the settings query and refreshes it explicitly", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      sections: [],
      features: [],
      partner_encryption_available: false,
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const store = createSettingsStore({
      api: api as never,
      at: (_key, _params, fallback) => fallback || "",
      onToast: vi.fn(),
      queryClient,
    });

    await store.loadSettings();
    await store.loadSettings();
    expect(api).toHaveBeenCalledTimes(1);

    await store.loadSettings({ refresh: true });
    expect(api).toHaveBeenCalledTimes(2);
    queryClient.clear();
  });

  it("keeps the saved value visible, then reports successful persistence", async () => {
    const api = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        sections: [
          {
            id: "general",
            fields: [
              {
                key: "WEBAPP_TITLE",
                label: "Title",
                overridden: false,
                value: "Old title",
              },
            ],
          },
        ],
      })
      .mockResolvedValueOnce({ ok: true, applied: 1, not_applied: [], reverted: 0 })
      .mockResolvedValueOnce({
        ok: true,
        sections: [
          {
            id: "general",
            fields: [
              {
                key: "WEBAPP_TITLE",
                label: "Title",
                overridden: true,
                value: "New title",
              },
            ],
          },
        ],
      });
    const onToast = vi.fn();
    const store = createSettingsStore({
      api: api as never,
      at: (_key, _params, fallback) => fallback || "",
      onToast,
    });

    await store.loadSettings();
    store.markDirty("WEBAPP_TITLE", "New title");
    const onSettingsSaved = vi.fn(() => {
      expect(store.settingsSections[0].fields[0].value).toBe("New title");
      expect(store.settingsSections[0].fields[0].overridden).toBe(true);
    });

    await expect(store.saveSettings(onSettingsSaved)).resolves.toBe(true);

    expect(onSettingsSaved).toHaveBeenCalledOnce();
    expect(onToast).toHaveBeenCalledWith("Settings saved");
    expect(store.settingsSections[0].fields[0].value).toBe("New title");
  });
});
