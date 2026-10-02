import { describe, expect, it, vi } from "vitest";

import { createBackupsStore } from "./backupsStore.svelte";

describe("backupsStore", () => {
  function uploadingStore() {
    const archive = {
      name: "backup.zip",
      size_bytes: 6,
      has_database: true,
      has_compose: true,
      warnings: [],
    };
    const api = vi
      .fn()
      .mockImplementation(async (path: string) =>
        path === "/admin/backups/upload" ? { ok: true, archive } : { ok: true, archives: [archive] }
      );
    const onToast = vi.fn();
    const store = createBackupsStore({
      api,
      onToast,
      at: (key) => key,
    });
    return { store, api, onToast };
  }

  function multipartFiles() {
    const parts = [
      new File(["abc"], "backup.zip.part0001"),
      new File(["def"], "backup.zip.part0002"),
    ];
    const manifest = new File(
      [
        JSON.stringify({
          format: "remnawave-minishop-backup-parts",
          version: 1,
          archive_name: "backup.zip",
          size_bytes: 6,
          sha256: "a".repeat(64),
          parts: parts.map((file) => ({
            name: file.name,
            size_bytes: file.size,
            sha256: "b".repeat(64),
          })),
        }),
      ],
      "backup.zip.parts.json"
    );
    return [manifest, ...parts] as const;
  }

  it("uploads a legacy File as the existing single multipart file", async () => {
    const { store, api, onToast } = uploadingStore();
    const zip = new File(["zip"], "backup.zip");
    expect(await store.uploadArchive(zip)).toMatchObject({ name: "backup.zip" });
    const options = api.mock.calls[0][1] as RequestInit;
    expect(api.mock.calls[0][0]).toBe("/admin/backups/upload");
    expect(options.method).toBe("POST");
    expect((options.body as FormData).getAll("file")).toEqual([zip]);
    expect(store.archives).toHaveLength(1);
    expect(onToast).toHaveBeenCalledWith("backups_upload_done");
    expect(store.backupsUploading).toBe(false);
  });

  it("uploads every selected file under the repeated file field", async () => {
    const { store, api } = uploadingStore();
    const files = multipartFiles();
    expect(await store.uploadArchive(files)).toMatchObject({ name: "backup.zip" });
    const body = (api.mock.calls[0][1] as RequestInit).body as FormData;
    expect([...body.keys()]).toEqual(["file", "file", "file"]);
    expect(body.getAll("file")).toEqual(files);
  });

  it("rejects incomplete, mixed and malformed files before any API call", async () => {
    const { store, api, onToast } = uploadingStore();
    const [manifest, first, second] = multipartFiles();
    for (const [files, error] of [
      [[manifest, first], "backups_upload_missing_parts"],
      [
        [manifest, first, second, new File(["zip"], "backup.zip")],
        "backups_upload_invalid_selection",
      ],
      [[new File(["{}"], manifest.name), first, second], "backups_upload_invalid_manifest"],
    ] as const) {
      expect(await store.uploadArchive(files)).toBeNull();
      expect(onToast).toHaveBeenLastCalledWith(error);
      expect(store.backupsUploading).toBe(false);
    }
    expect(api).not.toHaveBeenCalled();
  });

  it("lets the server reject checksum corruption and localizes its response", async () => {
    const { store, api, onToast } = uploadingStore();
    api.mockResolvedValue({ ok: false, error: "invalid_backup_parts" });
    expect(await store.uploadArchive(multipartFiles())).toBeNull();
    expect(onToast).toHaveBeenCalledWith("error_invalid_backup_parts");
    expect(api).toHaveBeenCalledTimes(1);
    expect(store.backupsUploading).toBe(false);
  });

  it("reports network failure and permits retrying the same set", async () => {
    const { store, api, onToast } = uploadingStore();
    api.mockRejectedValueOnce(new Error("connection closed"));
    const files = multipartFiles();
    expect(await store.uploadArchive(files)).toBeNull();
    expect(store.backupsUploading).toBe(false);
    expect(onToast).toHaveBeenCalledWith("backups_upload_failed");
    expect(await store.uploadArchive(files)).toMatchObject({ name: "backup.zip" });
  });

  it("keeps a created archive available and reports delivery warnings", async () => {
    const { store, api, onToast } = uploadingStore();
    const warning = "Archive created; delivery failed";
    api.mockResolvedValueOnce({
      ok: true,
      archive: { name: "backup.zip", size_bytes: 6, warnings: [] },
      result: { archive_name: "backup.zip", warnings: [warning] },
    });
    expect(await store.createBackup()).toMatchObject({ name: "backup.zip" });
    expect(onToast.mock.calls).toEqual([["backups_create_done"], [warning]]);
    expect(store.lastCreated).toMatchObject({ warnings: [warning] });
    expect(store.archives).toHaveLength(1);
    expect(store.backupsCreating).toBe(false);
  });

  it("loads file summaries without content inspection", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      backup_dir: "data/backups",
      archives: [
        {
          name: "minishop-demo.zip",
          size_bytes: 4096,
          modified_at: "2026-09-02T00:00:00Z",
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
      { name: "minishop-demo.zip", size_bytes: 4096, modified_at: "2026-09-02T00:00:00Z" },
    ]);
  });

  it("prefers current archive content flags over legacy aliases", async () => {
    const api = vi.fn().mockResolvedValue({
      ok: true,
      archive: {
        name: "minishop-current.zip",
        size_bytes: 4096,
        has_database: false,
        has_compose: false,
        contains_database: true,
        contains_compose: true,
        warnings: [],
      },
    });
    const store = createBackupsStore({
      api,
      onToast: vi.fn(),
      at: (_key: string, _params?: Record<string, unknown>, fallback?: string) => fallback || _key,
    });

    const inspected = await store.inspectArchive("minishop-current.zip");

    expect(inspected).toEqual(expect.objectContaining({ has_database: false, has_compose: false }));
  });
});
