import copy
import io
import json
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile, ZipInfo

import pytest

from bot.plugins.extensions import (
    BackupContributor,
    ExtensionContributions,
    ExtensionError,
    JobHandler,
)
from bot.plugins.extensions.backups import prepare_extensions, snapshot_extensions
from bot.plugins.extensions.registry import ExtensionRegistry, set_registry
from bot.plugins.package_user_ui import validate_user_frontend


@pytest.fixture(autouse=True)
def registry():
    value = ExtensionRegistry()
    set_registry(value)
    yield value
    set_registry(ExtensionRegistry())


def contributor(collect=None, validate=None, restore=None):
    return BackupContributor(
        "files", 1, collect or Mock(return_value={}), validate or Mock(), restore or Mock()
    )


def archive(*, version="1", filename="state.json", metadata=None):
    body = io.BytesIO()
    with ZipFile(body, "w") as output:
        output.writestr(
            "manifest.json",
            json.dumps(
                {
                    "extensions": {
                        "sample": {
                            "version": version,
                            "contributors": {"files": {"version": 1, "metadata": metadata or {}}},
                        }
                    }
                }
            ),
        )
        member = ZipInfo()
        member.filename = f"extensions/sample/files/{filename}"
        output.writestr(member, "{}")
    body.seek(0)
    return ZipFile(body)


def test_registration_is_atomic_on_duplicate_ids(registry):
    callback = Mock()
    with pytest.raises(ExtensionError, match="duplicate_extension_identifier"):
        registry.register(
            "sample",
            "1",
            ExtensionContributions(
                jobs=(JobHandler("same", callback), JobHandler("same", callback))
            ),
        )
    assert registry.owners() == {}
    with pytest.raises(ExtensionError, match="reserved"):
        registry.register("core", "1", ExtensionContributions())


def test_restore_rejects_missing_plugin_and_changed_version_before_callbacks(registry, tmp_path):
    with archive() as source, pytest.raises(ExtensionError, match="unavailable"):
        prepare_extensions(source, tmp_path)
    restore = Mock()
    registry.register(
        "sample", "2", ExtensionContributions(backups=(contributor(restore=restore),))
    )
    with archive() as source, pytest.raises(ExtensionError, match="version_mismatch"):
        prepare_extensions(source, tmp_path)
    restore.assert_not_called()


@pytest.mark.parametrize(
    "filename", ["../escape", "folder/../../escape", "C:escape", "folder\\escape", "file."]
)
def test_restore_rejects_unsafe_names(registry, tmp_path, filename):
    registry.register("sample", "1", ExtensionContributions(backups=(contributor(),)))
    with archive(filename=filename) as source, pytest.raises(ExtensionError, match="unsafe"):
        prepare_extensions(source, tmp_path)


def test_preflight_validates_without_restoring(registry, tmp_path):
    validate, restore = Mock(), Mock()
    registry.register(
        "sample",
        "1",
        ExtensionContributions(backups=(contributor(validate=validate, restore=restore),)),
    )
    with archive(metadata={"revision": 3}) as source:
        result = prepare_extensions(source, tmp_path)
    validate.assert_called_once_with(tmp_path / "extensions/sample/files", {"revision": 3})
    restore.assert_not_called()
    assert len(result) == 1


def test_backup_snapshots_versions_even_without_file_contributors(registry, tmp_path):
    def collect(path: Path):
        (path / "state.json").write_text("{}", encoding="utf-8")
        return {"schema": 1}

    registry.register("empty", "1", ExtensionContributions())
    registry.register(
        "sample", "1", ExtensionContributions(backups=(contributor(collect=collect),))
    )
    snapshot = snapshot_extensions(tmp_path)
    assert set(snapshot) == {"sample", "empty"}
    assert (tmp_path / "extensions/sample/files/state.json").read_text(encoding="utf-8") == "{}"


def test_legacy_backup_needs_no_plugins(tmp_path):
    body = io.BytesIO()
    with ZipFile(body, "w") as output:
        output.writestr("manifest.json", "{}")
    body.seek(0)
    with ZipFile(body) as source:
        assert prepare_extensions(source, tmp_path) == []


USER_UI = {
    "entry": "user.js",
    "pages": [{"id": "devices", "view": "devices", "label": "Devices", "icon": "device"}],
}


def test_user_surface_has_named_navigation_and_can_be_hidden():
    validate_user_frontend(USER_UI, {"frontend/user.js": "digest"})
    hidden = copy.deepcopy(USER_UI)
    hidden["pages"][0]["navigation"] = "hidden"
    validate_user_frontend(hidden, {"frontend/user.js": "digest"})


@pytest.mark.parametrize(
    "change",
    [
        {"id": "../admin"},
        {"icon": "<svg/>"},
        {"target": "admin"},
        {"navigation": "unknown"},
        {"order": True},
        {"label": ""},
    ],
)
def test_user_manifest_rejects_invalid_descriptors(change):
    value = copy.deepcopy(USER_UI)
    value["pages"][0].update(change)
    with pytest.raises(ValueError):
        validate_user_frontend(value, {"frontend/user.js": "digest"})


def test_user_manifest_cannot_reference_undeclared_assets():
    with pytest.raises(ValueError, match="asset"):
        validate_user_frontend(USER_UI, {"frontend/admin.js": "digest"})
