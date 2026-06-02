import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install.sh"


def test_shell_installer_help_does_not_require_python():
    if not shutil.which("sh"):
        pytest.skip("sh is not available on this platform")

    result = subprocess.run(
        ["sh", str(INSTALL_SCRIPT), "--help"],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "MINISHOP_INSTALL_REPO" in result.stdout
    assert "dry-run" in result.stdout
    assert "LEGACY_TGSHOP_SOURCE_DSN" in result.stdout


def test_shell_installer_is_the_only_install_entrypoint():
    assert INSTALL_SCRIPT.exists()
    assert not (REPO_ROOT / "scripts" / "install.py").exists()


def test_shell_installer_downloads_raw_files_and_runs_import_in_container():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert script.startswith("#!/bin/sh")
    assert "raw.githubusercontent.com" in script
    assert "git clone" not in script
    assert "backend python backend/scripts/import_legacy.py" in script
    assert "--dry-run" in script
    assert "Install new stack and run legacy migration" in script


def test_shell_installer_supports_legacy_tgshop_volume_and_dsn_paths():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Legacy remnawave-tg-shop" in script
    assert "remnawave-tg-shop-db-data" in script
    assert "remnawave-minishop-db-data" in script
    assert "pg_dump --clean --if-exists" in script
    assert "run_compose run --rm migrate" in script
