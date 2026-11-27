"""Image-native blacklist selection uses the ordinary plugin generation lifecycle."""

from pathlib import Path

from bot.plugins import packages, shipped
from bot.plugins.package_backup import snapshot_packages


def test_bundled_blacklist_lifecycle(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "image"
    dist.mkdir()
    monkeypatch.setattr(shipped, "DIST", dist)
    root = tmp_path / "store"
    monkeypatch.setenv("MINISHOP_PLUGIN_STORE", str(root))
    monkeypatch.delenv("MINISHOP_PLUGIN_GENERATION", raising=False)
    manifest = dist / "plugin.json"
    manifest.write_text('{"version":"1.2.0","publisher":"3252a8"}', encoding="utf-8")
    shipped.blacklist_installation.cache_clear()
    try:
        packages.bootstrap_image_package(root, "backend")
        state = packages.read_state(root)
        entry = state["installations"][shipped.BLACKLIST_ID]
        assert not entry["enabled"] and not packages.managed_entry_points(root)
        assert snapshot_packages(root, tmp_path / "backup")
        assert shipped.release_directory(root, shipped.BLACKLIST_ID, entry["digest"]) == dist

        packages.set_enabled(root, shipped.BLACKLIST_ID, True, 42, state["generation"])
        packages.bootstrap_image_package(root, "worker")
        points = packages.managed_entry_points(root)
        assert len(points) == 1 and points[0].load().name == shipped.BLACKLIST_ID
        manifest.write_text('{"version":"1.2.1","publisher":"3252a8"}', encoding="utf-8")
        shipped.blacklist_installation.cache_clear()
        packages.bootstrap_image_package(root, "backend")
        updated = packages.read_state(root)
        assert updated["installations"][shipped.BLACKLIST_ID]["enabled"]
        assert updated["generation"] == state["generation"] + 2
        packages.set_enabled(root, shipped.BLACKLIST_ID, False, 42, updated["generation"])
        packages.bootstrap_image_package(root, "backend")
        assert not packages.managed_entry_points(root)
    finally:
        shipped.blacklist_installation.cache_clear()
