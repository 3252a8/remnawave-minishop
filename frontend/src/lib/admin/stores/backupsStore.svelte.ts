import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiClient,
  type PostPayload,
  buildAdminBackupsCreatePath,
  buildAdminBackupsPath,
  buildAdminBackupsRestorePath,
  buildAdminBackupsUploadPath,
} from "../../webapp/publicApi";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = ApiClient["api"];
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type BackupRestorePayload = PostPayload<"/api/admin/backups/restore">;

export type BackupArchive = {
  name: string;
  size_bytes: number;
  created_at?: string;
  created_at_local?: string;
  modified_at?: string;
  has_database: boolean;
  has_compose: boolean;
  warnings: string[];
};
export type BackupRestoreResult = Record<string, unknown> & {
  compose_pre_restore_archive?: string;
};
export type BackupsState = {
  archives: BackupArchive[];
  backupDir: string;
  backupsLoading: boolean;
  backupsCreating: boolean;
  backupsUploading: boolean;
  backupsRestoring: boolean;
  lastCreated: BackupRestoreResult | null;
  lastRestore: BackupRestoreResult | null;
};
type BackupsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type BackupsStore = BackupsState & {
  loadArchives: () => Promise<void>;
  createBackup: () => Promise<BackupArchive | null>;
  uploadArchive: (file: File | null | undefined) => Promise<BackupArchive | null>;
  restoreArchive: (options: {
    archiveName: string;
    restoreDatabase: boolean;
    restoreCompose: boolean;
  }) => Promise<boolean>;
};

function isOkResponse<T extends { ok: true }>(response: T | AdminErrorResponse): response is T {
  return response.ok === true;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function normalizeArchive(value: unknown): BackupArchive | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const archive = value as Record<string, unknown>;
  return {
    name: typeof archive.name === "string" ? archive.name : "",
    size_bytes: typeof archive.size_bytes === "number" ? archive.size_bytes : 0,
    created_at: typeof archive.created_at === "string" ? archive.created_at : undefined,
    created_at_local:
      typeof archive.created_at_local === "string" ? archive.created_at_local : undefined,
    modified_at: typeof archive.modified_at === "string" ? archive.modified_at : undefined,
    has_database: Boolean(archive.has_database),
    has_compose: Boolean(archive.has_compose),
    warnings: asStringArray(archive.warnings),
  };
}

function normalizeArchives(archives: unknown): BackupArchive[] {
  return Array.isArray(archives)
    ? archives.flatMap((archive) => {
        const normalized = normalizeArchive(archive);
        return normalized ? [normalized] : [];
      })
    : [];
}

function normalizeRestoreResult(value: unknown): BackupRestoreResult | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as BackupRestoreResult;
}

export function createBackupsStore({ api, onToast, at }: BackupsStoreOptions): BackupsStore {
  const state = $state<BackupsStore>({
    archives: [],
    backupDir: "",
    backupsLoading: false,
    backupsCreating: false,
    backupsUploading: false,
    backupsRestoring: false,
    lastCreated: null,
    lastRestore: null,
    loadArchives,
    createBackup,
    uploadArchive,
    restoreArchive,
  });

  function updateState(updater: (snapshot: BackupsStore) => BackupsStore): void {
    const next = updater(state);
    if (next === state) return;
    Object.assign(state, next);
  }

  async function loadArchives(): Promise<void> {
    updateState((s) => ({ ...s, backupsLoading: true }));
    try {
      const data = await api(buildAdminBackupsPath());
      if (isOkResponse(data)) {
        const result = unwrap(data);
        updateState((s) => ({
          ...s,
          archives: normalizeArchives(result.archives),
          backupDir: result.backup_dir || "",
        }));
      } else {
        onToast(
          adminErrorMessage(data, at, at("backups_load_failed", {}, "Failed to load backups"))
        );
      }
    } finally {
      updateState((s) => ({ ...s, backupsLoading: false }));
    }
  }

  async function createBackup(): Promise<BackupArchive | null> {
    updateState((s) => ({ ...s, backupsCreating: true, lastCreated: null }));
    try {
      const data = await api(buildAdminBackupsCreatePath(), {
        method: "POST",
      });
      if (isOkResponse(data)) {
        const result = unwrap(data);
        updateState((s) => ({ ...s, lastCreated: normalizeRestoreResult(result.result) }));
        onToast(at("backups_create_done", {}, "Backup created"));
        await loadArchives();
        return normalizeArchive(result.archive);
      }
      onToast(
        adminErrorMessage(data, at, at("backups_create_failed", {}, "Failed to create backup"))
      );
      return null;
    } finally {
      updateState((s) => ({ ...s, backupsCreating: false }));
    }
  }

  async function uploadArchive(file: File | null | undefined): Promise<BackupArchive | null> {
    if (!file) return null;
    updateState((s) => ({ ...s, backupsUploading: true }));
    try {
      const body = new FormData();
      body.append("file", file);
      const data = await api(buildAdminBackupsUploadPath(), {
        method: "POST",
        body,
      });
      if (isOkResponse(data)) {
        const result = unwrap(data);
        onToast(at("backups_upload_done", {}, "Archive uploaded"));
        await loadArchives();
        return normalizeArchive(result.archive);
      }
      onToast(
        adminErrorMessage(data, at, at("backups_upload_failed", {}, "Failed to upload archive"))
      );
      return null;
    } finally {
      updateState((s) => ({ ...s, backupsUploading: false }));
    }
  }

  async function restoreArchive({
    archiveName,
    restoreDatabase,
    restoreCompose,
  }: {
    archiveName: string;
    restoreDatabase: boolean;
    restoreCompose: boolean;
  }): Promise<boolean> {
    const archive_name = String(archiveName || "").trim();
    if (!archive_name) {
      onToast(at("backups_select_archive", {}, "Select an archive"));
      return false;
    }
    if (!restoreDatabase && !restoreCompose) {
      onToast(at("backups_select_target", {}, "Select what to restore"));
      return false;
    }

    updateState((s) => ({ ...s, backupsRestoring: true, lastRestore: null }));
    try {
      const payload: BackupRestorePayload = {
        archive_name,
        restore_database: Boolean(restoreDatabase),
        restore_compose: Boolean(restoreCompose),
        confirm: true,
      };
      const data = await api(buildAdminBackupsRestorePath(), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (isOkResponse(data)) {
        const result = unwrap(data);
        updateState((s) => ({ ...s, lastRestore: normalizeRestoreResult(result.result) }));
        onToast(at("backups_restore_done", {}, "Restore completed"));
        return true;
      }
      onToast(adminErrorMessage(data, at, at("backups_restore_failed", {}, "Restore failed")));
      return false;
    } finally {
      updateState((s) => ({ ...s, backupsRestoring: false }));
    }
  }

  return state;
}
