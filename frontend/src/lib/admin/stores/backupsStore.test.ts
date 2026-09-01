import { describe, expect, it, vi } from "vitest";

import { createBackupsStore } from "./backupsStore.svelte";

describe("backupsStore", () => {
  it("normalizes legacy archive content flags", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      backup_dir: "data/backups",
      archives: [
        {
          name: "minishop-demo.zip",
          size_bytes: 4096,
          created_at: "2026-09-02T00:00:00Z",
          contains_database: true,
          contains_compose: true,
          warnings: [],
        },
      ],
    });
    const store = createBackupsStore({
      api,
      onToast: vi.fn(),
      at: (_key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || _key,
    });

    await store.loadArchives();

    expect(store.archives).toEqual([
      expect.objectContaining({
        name: "minishop-demo.zip",
        has_database: true,
        has_compose: true,
      }),
    ]);
  });

  it("prefers current archive content flags over legacy aliases", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      backup_dir: "data/backups",
      archives: [
        {
          name: "minishop-current.zip",
          size_bytes: 4096,
          has_database: false,
          has_compose: false,
          contains_database: true,
          contains_compose: true,
          warnings: [],
        },
      ],
    });
    const store = createBackupsStore({
      api,
      onToast: vi.fn(),
      at: (_key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || _key,
    });

    await store.loadArchives();

    expect(store.archives[0]).toEqual(
      expect.objectContaining({ has_database: false, has_compose: false })
    );
  });
});
