from __future__ import annotations

import json
from pathlib import Path

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
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_dev_stand_env_matches_latest_lock() -> None:
    env = _read_env(DEV_DIR / "remnawave-dev.env.example")
    lock = _read_lock(DEV_DIR / "remnawave-versions.lock.json")

    assert env["REMNAWAVE_STAND_PRESET"] == lock["remnawave_panel"]
    for env_key, lock_key in VERSION_KEYS.items():
        assert env[env_key] == lock[lock_key]


def test_remnawave_dev_stand_presets_match_locks_and_use_isolated_volumes() -> None:
    preset_dirs = sorted(path for path in PRESETS_DIR.iterdir() if path.is_dir())
    assert {"2.7.4", "2.8.0"}.issubset({path.name for path in preset_dirs})

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
