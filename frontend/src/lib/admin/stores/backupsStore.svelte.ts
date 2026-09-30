import { adminErrorMessage } from "../errors.js";
import {
  unwrap,
  type ApiClient,
  type PostPayload,
  buildApiUrl,
  buildAdminBackupDetailPath,
  buildAdminBackupDownloadPath,
  buildAdminBackupsCreatePath,
  buildAdminBackupsPath,
  buildAdminBackupsRestorePath,
  buildAdminBackupsUploadPath,
  buildBackupRestoreStatusPath,
} from "../../webapp/publicApi";

type AdminErrorResponse = { ok?: false; error?: string; message?: string; detail?: string };
type AdminApi = ApiClient["api"];
type ToastFn = (message: string) => void;
type TranslateFn = (key: string, params?: Record<string, unknown>, fallback?: string) => string;
type BackupRestorePayload = PostPayload<"/api/admin/backups/restore">;

export type BackupArchiveSummary = {
  name: string;
  size_bytes: number;
  modified_at?: string;
};
export type BackupArchive = BackupArchiveSummary & {
  created_at?: string;
  created_at_local?: string;
  has_database: boolean;
  has_compose: boolean;
  source_panel_api_url?: string;
  current_panel_api_url?: string;
  warnings: string[];
};
export type BackupRestoreResult = Record<string, unknown> & {
  compose_pre_restore_archive?: string;
  database_pre_restore_archive?: string;
};
export type BackupsState = {
  archives: BackupArchiveSummary[];
  backupDir: string;
  backupsLoading: boolean;
  backupsCreating: boolean;
  backupsUploading: boolean;
  backupsRestoring: boolean;
  lastCreated: BackupRestoreResult | null;
  lastRestore: BackupRestoreResult | null;
  restoreStatus: string;
  restoreError: string;
};
type BackupsStoreOptions = {
  api: AdminApi;
  onToast: ToastFn;
  at: TranslateFn;
};
export type BackupsStore = BackupsState & {
  loadArchives: () => Promise<void>;
  inspectArchive: (name: string) => Promise<BackupArchive | null>;
  createBackup: () => Promise<BackupArchive | null>;
  uploadArchive: (file: File | null | undefined) => Promise<BackupArchive | null>;
  downloadArchive: (name: string) => Promise<void>;
  resumeRestore: () => Promise<void>;
  restoreArchive: (options: {
    archiveName: string;
    restoreDatabase: boolean;
    restoreCompose: boolean;
    resetPanelOrigin: boolean;
    confirmation: string;
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

function normalizeArchiveSummary(value: unknown): BackupArchiveSummary | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const archive = value as Record<string, unknown>;
  if (typeof archive.name !== "string" || !archive.name) return null;
  return {
    name: archive.name,
    size_bytes: typeof archive.size_bytes === "number" ? archive.size_bytes : 0,
    modified_at: typeof archive.modified_at === "string" ? archive.modified_at : undefined,
  };
}

function normalizeArchive(value: unknown): BackupArchive | null {
  const summary = normalizeArchiveSummary(value);
  if (!summary || !value || typeof value !== "object" || Array.isArray(value)) return null;
  const archive = value as Record<string, unknown>;
  return {
    ...summary,
    created_at: typeof archive.created_at === "string" ? archive.created_at : undefined,
    created_at_local:
      typeof archive.created_at_local === "string" ? archive.created_at_local : undefined,
    has_database: Boolean(archive.has_database ?? archive.contains_database),
    has_compose: Boolean(archive.has_compose ?? archive.contains_compose),
    source_panel_api_url:
      typeof archive.source_panel_api_url === "string" ? archive.source_panel_api_url : undefined,
    current_panel_api_url:
      typeof archive.current_panel_api_url === "string" ? archive.current_panel_api_url : undefined,
    warnings: asStringArray(archive.warnings),
  };
}

function normalizeArchives(archives: unknown): BackupArchiveSummary[] {
  return Array.isArray(archives)
    ? archives.flatMap((archive) => {
        const normalized = normalizeArchiveSummary(archive);
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
    restoreStatus: "",
    restoreError: "",
    loadArchives,
    inspectArchive,
    createBackup,
    uploadArchive,
    downloadArchive,
    resumeRestore,
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

  async function inspectArchive(name: string): Promise<BackupArchive | null> {
    try {
      const data = await api(buildAdminBackupDetailPath(name));
      if (isOkResponse(data)) return normalizeArchive(unwrap(data).archive);
      onToast(
        adminErrorMessage(data, at, at("backups_inspect_failed", {}, "Failed to inspect backup"))
      );
      return null;
    } catch {
      onToast(at("backups_inspect_failed", {}, "Failed to inspect backup"));
      return null;
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

  async function downloadArchive(name: string): Promise<void> {
    const anchor = document.createElement("a");
    anchor.href = buildApiUrl(buildAdminBackupDownloadPath(name));
    anchor.download = name;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  }

  async function pollRestore(id: string, token: string, archiveName: string): Promise<boolean> {
    updateState((s) => ({ ...s, backupsRestoring: true, restoreStatus: "queued" }));
    while (true) {
      try {
        const data = await api(buildBackupRestoreStatusPath(id), {
          headers: { "X-Backup-Restore-Token": token },
        });
        if (data.ok === true && data.job && typeof data.job === "object") {
          const job = data.job as Record<string, unknown>;
          const status = String(job.status || "");
          updateState((s) => ({ ...s, restoreStatus: status }));
          if (status === "completed") {
            sessionStorage.removeItem("minishop-backup-restore");
            updateState((s) => ({
              ...s,
              backupsRestoring: false,
              lastRestore: { archive_name: archiveName, database_restored: true },
            }));
            onToast(at("backups_restore_done", {}, "Restore completed"));
            await loadArchives();
            return true;
          }
          if (status === "failed" || status === "recovery_required") {
            sessionStorage.removeItem("minishop-backup-restore");
            const error = String(job.error || status);
            updateState((s) => ({
              ...s,
              backupsRestoring: false,
              restoreError: error,
            }));
            onToast(at("backups_restore_failed", {}, "Restore failed"));
            return false;
          }
        }
      } catch {
        // The API is briefly unavailable while backend and worker are stopped.
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  async function resumeRestore(): Promise<void> {
    const saved = sessionStorage.getItem("minishop-backup-restore");
    if (!saved) return;
    try {
      const { id, token, archiveName } = JSON.parse(saved) as Record<string, string>;
      if (id && token && archiveName) await pollRestore(id, token, archiveName);
    } catch {
      sessionStorage.removeItem("minishop-backup-restore");
    }
  }

  async function restoreArchive({
    archiveName,
    restoreDatabase,
    restoreCompose,
    resetPanelOrigin,
    confirmation,
  }: {
    archiveName: string;
    restoreDatabase: boolean;
    restoreCompose: boolean;
    resetPanelOrigin: boolean;
    confirmation: string;
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

    updateState((s) => ({ ...s, backupsRestoring: true, lastRestore: null, restoreError: "" }));
    try {
      const payload: BackupRestorePayload = {
        archive_name,
        restore_database: Boolean(restoreDatabase),
        restore_compose: Boolean(restoreCompose),
        reset_panel_origin: Boolean(resetPanelOrigin),
        confirm: true,
        confirmation,
      };
      const data = await api(buildAdminBackupsRestorePath(), {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (isOkResponse(data)) {
        const result = unwrap(data);
        if (restoreDatabase && result.job && result.status_token) {
          const job = result.job as { id: string };
          sessionStorage.setItem(
            "minishop-backup-restore",
            JSON.stringify({ id: job.id, token: result.status_token, archiveName: archive_name })
          );
          return await pollRestore(job.id, result.status_token, archive_name);
        }
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
