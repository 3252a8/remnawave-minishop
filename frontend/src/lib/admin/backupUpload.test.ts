import { describe, expect, it, vi } from "vitest";

import { validateBackupUpload } from "./backupUpload.js";

function manifest() {
  return {
    format: "remnawave-minishop-backup-parts",
    version: 1,
    archive_name: "backup.zip",
    size_bytes: 6,
    sha256: "a".repeat(64),
    parts: [
      { name: "backup.zip.part0001", size_bytes: 3, sha256: "b".repeat(64) },
      { name: "backup.zip.part0002", size_bytes: 3, sha256: "c".repeat(64) },
    ],
  };
}

function manifestFile(value: unknown = manifest(), name = "backup.zip.parts.json") {
  return new File([JSON.stringify(value)], name, { type: "application/json" });
}

const part = (index: number, content = "abc") =>
  new File([content], `backup.zip.part${String(index).padStart(4, "0")}`);

describe("backup upload selection", () => {
  it("keeps the single ZIP path without reading the archive", async () => {
    const zip = new File(["zip"], "backup.zip");
    const read = vi.spyOn(zip, "text");
    expect(await validateBackupUpload([zip])).toBeNull();
    expect(read).not.toHaveBeenCalled();
  });

  it("accepts all parts selected in any order and only reads the manifest", async () => {
    const first = part(1);
    const second = part(2);
    const readFirst = vi.spyOn(first, "text");
    const readSecond = vi.spyOn(second, "arrayBuffer");
    expect(await validateBackupUpload([second, manifestFile(), first])).toBeNull();
    expect(readFirst).not.toHaveBeenCalled();
    expect(readSecond).not.toHaveBeenCalled();
  });

  it("names missing parts when only a manifest or an incomplete set is selected", async () => {
    expect(await validateBackupUpload([manifestFile(), part(1)])).toMatchObject({
      key: "backups_upload_missing_parts",
      params: { files: "backup.zip.part0002" },
    });
    expect(await validateBackupUpload([manifestFile()])).toMatchObject({
      key: "backups_upload_missing_parts",
      params: { files: "backup.zip.part0001, backup.zip.part0002" },
    });
  });

  it("rejects ZIPs mixed with parts and sets without exactly one manifest", async () => {
    const zip = new File(["zip"], "backup.zip");
    for (const files of [
      [],
      [part(1), part(2)],
      [zip, part(1)],
      [zip, manifestFile(), part(1), part(2)],
      [manifestFile(), manifestFile(manifest(), "other.zip.parts.json")],
    ])
      expect(await validateBackupUpload(files)).toMatchObject({
        key: "backups_upload_invalid_selection",
      });
  });

  it("rejects extra files and duplicate selection names", async () => {
    expect(
      await validateBackupUpload([manifestFile(), part(1), part(2), new File(["x"], "other.part")])
    ).toMatchObject({
      key: "backups_upload_unexpected_parts",
      params: { files: "other.part" },
    });
    expect(await validateBackupUpload([manifestFile(), part(1), part(1)])).toMatchObject({
      key: "backups_upload_duplicate_files",
    });
  });

  it("identifies a truncated part without reading it", async () => {
    expect(await validateBackupUpload([manifestFile(), part(1), part(2, "ab")])).toMatchObject({
      key: "backups_upload_part_size_mismatch",
      params: { file: "backup.zip.part0002" },
    });
  });

  it("rejects unreadable, invalid and oversized manifests before upload", async () => {
    const unreadable = manifestFile();
    vi.spyOn(unreadable, "text").mockRejectedValue(new Error("file unavailable"));
    const oversized = new File([new Uint8Array(1024 ** 2 + 1)], "backup.zip.parts.json");
    const read = vi.spyOn(oversized, "text");
    for (const file of [
      new File(["{"], "backup.zip.parts.json"),
      manifestFile(null),
      manifestFile([]),
      unreadable,
      oversized,
    ])
      expect(await validateBackupUpload([file, part(1), part(2)])).toMatchObject({
        key: "backups_upload_invalid_manifest",
      });
    expect(read).not.toHaveBeenCalled();
  });

  it.each([
    ["format", { format: "other-backup" }],
    ["version", { version: 2 }],
    ["path", { archive_name: "../backup.zip" }],
    ["filename", { archive_name: "other.zip" }],
    ["archive checksum", { sha256: "invalid" }],
    ["size", { size_bytes: "6" }],
    ["total", { size_bytes: 7 }],
    ["empty parts", { parts: [] }],
    ["part checksum", { parts: [{ ...manifest().parts[0], sha256: "invalid" }] }],
    ["part order", { parts: [...manifest().parts].reverse() }],
    ["duplicate parts", { parts: [manifest().parts[0], manifest().parts[0]] }],
    ["part size", { parts: [{ ...manifest().parts[0], size_bytes: 0 }] }],
  ])("rejects corrupt %s metadata", async (_label, values) => {
    expect(
      await validateBackupUpload([manifestFile({ ...manifest(), ...values }), part(1), part(2)])
    ).toMatchObject({ key: "backups_upload_invalid_manifest" });
  });

  it("enforces the 2 GiB limit without allocating or reading large archives", async () => {
    const zip = new File(["zip"], "backup.zip");
    Object.defineProperty(zip, "size", { value: 2 * 1024 ** 3 + 1, configurable: true });
    expect(await validateBackupUpload([zip])).toMatchObject({ key: "backups_upload_too_large" });
    Object.defineProperty(zip, "size", { value: 2 * 1024 ** 3 });
    expect(await validateBackupUpload([zip])).toBeNull();
    expect(
      await validateBackupUpload([
        manifestFile({ ...manifest(), size_bytes: 2 * 1024 ** 3 + 1 }),
        part(1),
        part(2),
      ])
    ).toMatchObject({ key: "backups_upload_too_large" });
  });
});
