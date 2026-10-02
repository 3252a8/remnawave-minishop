const MAX_ARCHIVE_BYTES = 2 * 1024 ** 3;
const MAX_MANIFEST_BYTES = 1024 ** 2;
const MAX_PARTS = 10_000;

export type BackupUploadProblem = {
  key: string;
  params?: Record<string, unknown>;
  fallback: string;
};

const invalidSelection: BackupUploadProblem = {
  key: "backups_upload_invalid_selection",
  fallback: "Select one ZIP, or a manifest and all parts from one backup.",
};
const invalidManifest: BackupUploadProblem = {
  key: "backups_upload_invalid_manifest",
  fallback: "Invalid backup parts manifest. Download it again with every part.",
};
const tooLarge: BackupUploadProblem = {
  key: "backups_upload_too_large",
  fallback: "Backup archive exceeds the 2 GiB upload limit.",
};

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function positiveSize(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

function checksum(value: unknown): boolean {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

/** Check small metadata only. The server verifies the uploaded bytes and joins the parts. */
export async function validateBackupUpload(
  files: readonly File[]
): Promise<BackupUploadProblem | null> {
  if (!files.length) return invalidSelection;
  const selected = new Map(files.map((file) => [file.name, file]));
  if (selected.size !== files.length)
    return {
      key: "backups_upload_duplicate_files",
      fallback: "Selected files have duplicate names. Select each backup file once.",
    };

  if (files.length === 1 && files[0].name.toLowerCase().endsWith(".zip")) {
    if (!files[0].size) return invalidSelection;
    return files[0].size > MAX_ARCHIVE_BYTES ? tooLarge : null;
  }

  const manifests = files.filter((file) => file.name.endsWith(".zip.parts.json"));
  if (manifests.length !== 1 || files.some((file) => file.name.toLowerCase().endsWith(".zip")))
    return invalidSelection;
  const manifestFile = manifests[0];
  if (!manifestFile.size || manifestFile.size > MAX_MANIFEST_BYTES) return invalidManifest;

  let manifest: Record<string, unknown> | null;
  try {
    manifest = record(JSON.parse(await manifestFile.text()));
  } catch {
    return invalidManifest;
  }
  if (
    !manifest ||
    manifest.format !== "remnawave-minishop-backup-parts" ||
    manifest.version !== 1 ||
    typeof manifest.archive_name !== "string" ||
    !manifest.archive_name.endsWith(".zip") ||
    /[/\\:\0]/.test(manifest.archive_name) ||
    manifestFile.name !== `${manifest.archive_name}.parts.json` ||
    !positiveSize(manifest.size_bytes) ||
    !checksum(manifest.sha256) ||
    !Array.isArray(manifest.parts) ||
    manifest.parts.length < 1 ||
    manifest.parts.length > MAX_PARTS
  )
    return invalidManifest;
  if (manifest.size_bytes > MAX_ARCHIVE_BYTES) return tooLarge;

  const parts = new Map<string, number>();
  for (const [index, value] of manifest.parts.entries()) {
    const part = record(value);
    const name = `${manifest.archive_name}.part${String(index + 1).padStart(4, "0")}`;
    if (!part || part.name !== name || !positiveSize(part.size_bytes) || !checksum(part.sha256))
      return invalidManifest;
    parts.set(name, part.size_bytes);
  }
  if ([...parts.values()].reduce((total, size) => total + size, 0) !== manifest.size_bytes)
    return invalidManifest;

  const unexpected = files.filter((file) => file !== manifestFile && !parts.has(file.name));
  if (unexpected.length)
    return {
      key: "backups_upload_unexpected_parts",
      params: { files: unexpected.map((file) => file.name).join(", ") },
      fallback: `These files do not belong to the selected backup: ${unexpected.map((file) => file.name).join(", ")}.`,
    };
  const missing = [...parts.keys()].filter((name) => !selected.has(name));
  if (missing.length)
    return {
      key: "backups_upload_missing_parts",
      params: { files: missing.join(", ") },
      fallback: `Missing backup parts: ${missing.join(", ")}. Select the manifest and every part together.`,
    };
  for (const [name, size] of parts) {
    if (selected.get(name)?.size !== size)
      return {
        key: "backups_upload_part_size_mismatch",
        params: { file: name },
        fallback: `Backup part size differs from the manifest: ${name}. Download the part again.`,
      };
  }
  return null;
}
