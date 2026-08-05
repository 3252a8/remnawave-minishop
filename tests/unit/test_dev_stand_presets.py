from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import jwt

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_DIR = REPO_ROOT / "deploy" / "dev"
PRESETS_DIR = DEV_DIR / "remnawave-stands"

VERSION_KEYS = {
    "REMNAWAVE_DEV_VERSION": "remnawave_panel",
    "REMNAWAVE_NODE_VERSION": "remnawave_node",
    "REMNAWAVE_SUBSCRIPTION_PAGE_VERSION": "subscription_page",
}
VOLUME_KEYS = (
    "DEV_MINISHOP_DB_VOLUME",
    "DEV_MINISHOP_REDIS_VOLUME",
    "REMNAWAVE_DEV_DB_VOLUME",
    "REMNAWAVE_DEV_VALKEY_SOCKET_VOLUME",
)


def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = raw_line.partition("=")
        assert separator, f"Invalid env line in {path}: {raw_line!r}"
        result[key] = value
    return result


def _read_lock(path: Path) -> dict[str, str]:
    data: dict[str, str] = json.loads(path.read_text(encoding="utf-8"))
    return data


def test_default_dev_stand_env_matches_latest_lock() -> None:
    env = _read_env(DEV_DIR / "remnawave-dev.env.example")
    lock = _read_lock(DEV_DIR / "remnawave-versions.lock.json")

    assert env["REMNAWAVE_STAND_PRESET"] == lock["remnawave_panel"]
    for env_key, lock_key in VERSION_KEYS.items():
        assert env[env_key] == lock[lock_key]


def test_default_panel_api_token_uses_app_secret() -> None:
    env = _read_env(DEV_DIR / "remnawave-dev.env.example")

    payload = jwt.decode(
        env["REMNAWAVE_DEV_API_TOKEN"],
        env["REMNAWAVE_DEV_APP_SECRET"],
        algorithms=["HS256"],
    )

    assert payload["role"] == "API"
    assert payload["uuid"] == "30000000-0000-4000-8000-000000000001"


def test_remnawave_overlay_uses_latest_panel_and_compatible_secret_names() -> None:
    compose = (REPO_ROOT / "docker-compose.remnawave-dev.yml").read_text(encoding="utf-8")
    lock = _read_lock(DEV_DIR / "remnawave-versions.lock.json")

    assert (
        f"image: remnawave/backend:${{REMNAWAVE_DEV_VERSION:-{lock['remnawave_panel']}}}" in compose
    )
    assert "APP_SECRET: ${REMNAWAVE_DEV_APP_SECRET:-" in compose
    assert "JWT_AUTH_SECRET: ${REMNAWAVE_DEV_APP_SECRET:-" in compose


def test_remnawave_dev_stand_presets_match_locks_and_use_isolated_volumes() -> None:
    preset_dirs = sorted(path for path in PRESETS_DIR.iterdir() if path.is_dir())
    assert {"2.7.4", "2.8.0", "2.8.1", "3.0.0", "3.1.0", "3.2.0", "3.2.1"}.issubset(
        {path.name for path in preset_dirs}
    )

    volumes_by_key: dict[str, dict[str, str]] = {key: {} for key in VOLUME_KEYS}
    for preset_dir in preset_dirs:
        env = _read_env(preset_dir / "stand.env")
        lock = _read_lock(preset_dir / "versions.lock.json")

        assert preset_dir.name == lock["remnawave_panel"]
        assert env["REMNAWAVE_STAND_PRESET"] == preset_dir.name
        for env_key, lock_key in VERSION_KEYS.items():
            assert env[env_key] == lock[lock_key]

        volume_values = {env[key] for key in VOLUME_KEYS}
        assert len(volume_values) == len(VOLUME_KEYS)

        for key in VOLUME_KEYS:
            volume = env[key]
            assert volume.endswith(preset_dir.name.replace(".", ""))
            assert volume not in volumes_by_key[key], (
                f"{key}={volume} is reused by both "
                f"{volumes_by_key[key].get(volume)} and {preset_dir.name}"
            )
            volumes_by_key[key][volume] = preset_dir.name


def test_upgrade_target_preserves_the_source_database_volume(tmp_path: Path) -> None:
    env_path = tmp_path / "upgrade.env"
    env_path.write_text(
        "\n".join(
            (
                "REMNAWAVE_STAND_PRESET=2.8.1",
                "REMNAWAVE_DEV_VERSION=2.8.1",
                "REMNAWAVE_DEV_DB_VOLUME=source-panel-db-281",
                "DEV_MINISHOP_DB_VOLUME=source-minishop-db-281",
                "",
            )
        ),
        encoding="utf-8",
    )
    process_env = dict(os.environ)
    process_env["REMNAWAVE_UPGRADE_ENV_PATH"] = str(env_path)

    subprocess.run(
        [
            "node",
            str(REPO_ROOT / "scripts" / "prepare_remnawave_upgrade_target.mjs"),
            "2.8.1",
            "3.2.1",
        ],
        check=True,
        cwd=REPO_ROOT,
        env=process_env,
        capture_output=True,
        text=True,
    )

    upgraded = _read_env(env_path)
    assert upgraded["REMNAWAVE_STAND_PRESET"] == "upgrade-2.8.1-to-3.2.1"
    assert upgraded["REMNAWAVE_DEV_VERSION"] == "3.2.1"
    assert upgraded["REMNAWAVE_DEV_DB_VOLUME"] == "source-panel-db-281"
    assert upgraded["DEV_MINISHOP_DB_VOLUME"] == "source-minishop-db-281"
    assert upgraded["REMNAWAVE_UPGRADE_FROM"] == "2.8.1"
    assert upgraded["REMNAWAVE_UPGRADE_TO"] == "3.2.1"


def test_dev_seed_matches_current_non_nullable_and_unique_contracts() -> None:
    seed = (DEV_DIR / "seed-minishop.sql").read_text(encoding="utf-8")

    assert "auto_renew_consent_version" in seed
    assert "is_auto_renew" in seed
    assert "ON CONFLICT (provider, provider_payment_id)" in seed
