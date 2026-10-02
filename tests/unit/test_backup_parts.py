import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from bot.services.backup_parts import BackupPartsError, join_backup, split_backup


@pytest.mark.parametrize("length", [1, 16, 17, 18, 34, 35, 200])
def test_parts_round_trip_preserves_all_bytes_and_checksums(tmp_path: Path, length: int) -> None:
    source = tmp_path / "source.zip"
    payload = bytes(range(200))[:length]
    source.write_bytes(payload)
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()

    parts, manifest = split_backup(source, parts_dir, part_bytes=17)
    metadata = json.loads(manifest.read_text())
    restored = join_backup(manifest)

    assert restored.read_bytes() == payload
    assert source.read_bytes() == payload
    assert metadata["sha256"] == hashlib.sha256(payload).hexdigest()
    assert [part.path.name for part in parts] == [record["name"] for record in metadata["parts"]]
    assert all(0 < part.size_bytes <= 17 for part in parts)
    assert all(part.size_bytes == part.path.stat().st_size for part in parts)
    assert len(parts) == (length + 16) // 17
    assert list(parts_dir.glob(".join-backup-*")) == []


@pytest.mark.parametrize("fault", ["missing", "corrupt", "larger", "smaller", "archive_hash"])
def test_invalid_parts_never_publish_an_output(tmp_path: Path, fault: str) -> None:
    source = tmp_path / "source.zip"
    source.write_bytes(bytes(range(70)))
    parts_dir = tmp_path / "parts"
    parts_dir.mkdir()
    parts, manifest = split_backup(source, parts_dir, part_bytes=17)
    if fault == "missing":
        parts[1].path.unlink()
    elif fault == "corrupt":
        parts[1].path.write_bytes(b"x" * 17)
    elif fault == "larger":
        parts[1].path.write_bytes(b"x" * 18)
    elif fault == "smaller":
        parts[1].path.write_bytes(b"x" * 16)
    else:
        data = json.loads(manifest.read_text())
        data["sha256"] = "0" * 64
        manifest.write_text(json.dumps(data))

    with pytest.raises(BackupPartsError):
        join_backup(manifest)

    assert not (parts_dir / source.name).exists()
    assert list(parts_dir.glob(".join-backup-*")) == []


@pytest.mark.parametrize("name", ["../escape", "/escape", "..\\escape", "C:escape", ".."])
def test_manifest_rejects_path_traversal(tmp_path: Path, name: str) -> None:
    source = tmp_path / "source.zip"
    source.write_bytes(b"data")
    _, manifest = split_backup(source, tmp_path, part_bytes=3)
    data = json.loads(manifest.read_text())
    data["parts"][0]["name"] = name
    manifest.write_text(json.dumps(data))

    with pytest.raises(BackupPartsError, match="unsafe filename"):
        join_backup(manifest, tmp_path / "restored.zip")


def test_manifest_rejects_duplicates_and_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    source.write_bytes(b"123456")
    _, manifest = split_backup(source, tmp_path, part_bytes=3)
    with pytest.raises(BackupPartsError, match="already exists"):
        join_backup(manifest)
    assert source.read_bytes() == b"123456"

    data = json.loads(manifest.read_text())
    data["parts"][1] = data["parts"][0]
    manifest.write_text(json.dumps(data))
    with pytest.raises(BackupPartsError, match="duplicate"):
        join_backup(manifest, tmp_path / "restored.zip")


def test_join_cli_reconstructs_downloaded_backup(tmp_path: Path) -> None:
    source = tmp_path / "source.zip"
    source.write_bytes(b"original ZIP bytes")
    _, manifest = split_backup(source, tmp_path, part_bytes=4)
    target = tmp_path / "restored.zip"
    result = subprocess.run(
        [sys.executable, "scripts/join-backup.py", str(manifest), "--output", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == source.read_bytes()
