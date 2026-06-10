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
    assert "Optional source Remnashop .env path" in script
    assert "--source-env-file /tmp/remnashop.env" in script
    assert "--dry-run" in script
    assert "Install new stack and run migration" in script
    assert "Run migration only" in script


def test_shell_installer_supports_legacy_tgshop_volume_and_dsn_paths():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "Old remnawave-tg-shop" in script
    assert "remnawave-tg-shop-db-data" in script
    assert "remnawave-minishop-db-data" in script
    assert "pg_dump --clean --if-exists" in script
    assert "run_compose run --rm migrate" in script


def test_shell_installer_only_prepares_data_mount_not_runtime_content():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert 'data_dir="$TARGET_DIR/data"' in script
    assert 'mkdir -p "$data_dir"' in script
    assert 'chown "$APP_UID:$APP_GID" "$data_dir"' in script
    assert "data_dir/themes" not in script
    assert "webapp-logo" not in script
    assert "webapp-emoji" not in script
    assert "locales-overrides.json" not in script


def test_shell_installer_prints_remnashop_webhook_checklist():
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")

    assert "remnashop_webhook_checklist" in script
    assert "Remnawave Panel -> WEBHOOK_URL" in script
    assert "PANEL_WEBHOOK_SECRET" in script
    assert "/webhook/panel" in script
    assert "/webhook/yookassa" in script
    assert "/webhook/wata" in script
    assert "/webhook/cryptopay" in script
    assert "/webhook/heleket" in script
    assert "/webhook/paykilla" in script
    assert "/webhook/freekassa" in script
    assert "/webhook/platega" in script
    assert "/tg/webhook" in script
