import zipfile
from pathlib import Path
from zipfile import ZipFile

from bot.services import backup_archive


def test_backup_zip_uses_maximum_deflate_compression(monkeypatch, tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "database.sql").write_text("repeated backup data\n" * 100, encoding="utf-8")
    archive_path = tmp_path / "backup.zip"
    captured: dict[str, object] = {}

    class RecordingZipFile(ZipFile):
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(backup_archive.zipfile, "ZipFile", RecordingZipFile)

    backup_archive.write_zip_from_directory(source_dir, archive_path)

    assert captured["compression"] == zipfile.ZIP_DEFLATED
    assert captured["compresslevel"] == 9
    with ZipFile(archive_path) as archive:
        assert archive.read("database.sql").decode("utf-8").startswith("repeated backup data")
