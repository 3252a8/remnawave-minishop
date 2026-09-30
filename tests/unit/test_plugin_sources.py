"""Public repository inputs stay inside the ready-artifact boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import make_mocked_request

from bot.app.web.admin_api_impl import plugin_packages
from bot.plugins import sources
from bot.plugins.packages import PluginPackageError
from bot.plugins.sources import _repository, _safe_url, release_version, repository_tracking_ref


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/example/plugin", ("github.com", "example/plugin")),
        ("https://gitlab.com/group/team/plugin", ("gitlab.com", "group/team/plugin")),
    ],
)
def test_public_repository_root(url: str, expected: tuple[str, str]) -> None:
    assert _repository(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/plugin",
        "https://user:secret@github.com/example/plugin",
        "https://github.com/example/plugin?token=secret",
        "https://github.com/example/plugin#anchor",
        "https://github.com/example/plugin/tree/main",
        "https://github.com/example/%2e%2e",
        "https://localhost/example/plugin",
        "https://127.0.0.1/example/plugin",
        "https://github.com:8443/example/plugin",
    ],
)
def test_rejects_untrusted_repository_inputs(url: str) -> None:
    with pytest.raises(PluginPackageError, match="invalid_repository_url"):
        _repository(url)


def test_download_hosts_are_separate_from_repository_inputs() -> None:
    _safe_url("https://raw.githubusercontent.com/example/plugin/" + "a" * 40 + "/plugin.zip")
    with pytest.raises(PluginPackageError, match="invalid_repository_url"):
        _repository("https://raw.githubusercontent.com/example/plugin")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.2.3", (1, 2, 3)),
        ("1.2.3-dev", None),
        ("01.2.3", None),
        ("v1.2.3", None),
        (None, None),
    ],
)
def test_update_badge_requires_a_stable_release_version(
    value: object, expected: tuple[int, int, int] | None
) -> None:
    assert release_version(value) == expected


@pytest.mark.parametrize("host", ["github.com", "gitlab.com"])
@pytest.mark.parametrize("ref", ["", "release/stable", "a" * 40])
@pytest.mark.parametrize("pinned", [False, True])
def test_package_snapshot_keeps_the_requested_tracking_ref(
    monkeypatch: pytest.MonkeyPatch, host: str, ref: str, pinned: bool
) -> None:
    async def scenario() -> None:
        archive = b"ready archive"
        calls: list[str] = []
        commit = "a" * 40 if pinned or ref == "a" * 40 else "b" * 40

        async def metadata(_session: object, url: str) -> dict[str, object]:
            calls.append(url)
            if "minishop-plugin.json" in url:
                return {
                    "schema_version": 1,
                    "artifact": "package.zip",
                    "sha256": hashlib.sha256(archive).hexdigest(),
                }
            if "/commits/" in url:
                return {"sha": commit, "id": commit}
            return {"default_branch": "main"}

        downloader = AsyncMock(return_value=archive)
        monkeypatch.setattr(sources, "TCPConnector", lambda **_kwargs: None)
        monkeypatch.setattr(sources, "ClientSession", lambda **_kwargs: AsyncMock())
        monkeypatch.setattr(sources, "_json", metadata)
        monkeypatch.setattr(sources, "_download", downloader)
        body, source = await sources.fetch_ready_package(
            f"https://{host}/example/plugin", ref, commit="a" * 40 if pinned else ""
        )
        assert body == archive
        assert source["ref"] == source["requested_ref"] == ref
        assert source["commit"] == commit
        assert downloader.await_args is not None
        assert commit in downloader.await_args.args[1]
        lookup = "a" * 40 if pinned else (ref or "main")
        assert any(url.endswith("/commits/" + lookup.replace("/", "%2F")) for url in calls)
        assert repository_tracking_ref(source) == ref

    asyncio.run(scenario())


@pytest.mark.parametrize("host", ["github.com", "gitlab.com"])
def test_empty_update_ref_follows_the_current_default_branch(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> None:
    async def scenario() -> None:
        calls: list[str] = []
        default_branch = "main"

        async def metadata(_session: object, url: str) -> dict[str, object]:
            calls.append(url)
            if "minishop-plugin.json" in url:
                return {"schema_version": 1, "sha256": "b" * 64, "version": "2.0.0"}
            return {"default_branch": default_branch}

        monkeypatch.setattr(sources, "TCPConnector", lambda **_kwargs: None)
        monkeypatch.setattr(sources, "ClientSession", lambda **_kwargs: AsyncMock())
        monkeypatch.setattr(sources, "_json", metadata)
        assert await sources.check_ready_package_release(f"https://{host}/example/plugin", "") == (
            "b" * 64,
            (2, 0, 0),
        )
        default_branch = "release/stable"
        await sources.check_ready_package_release(f"https://{host}/example/plugin", "")
        index_urls = [url for url in calls if "minishop-plugin.json" in url]
        assert "main" in index_urls[0]
        assert "release%2Fstable" in index_urls[1]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ({"ref": "main", "commit": "a" * 40}, "main"),
        ({"ref": "v1.2.3", "commit": "a" * 40}, "v1.2.3"),
        ({"ref": "a" * 40, "commit": "a" * 40}, ""),
        ({"ref": "a" * 40, "commit": "a" * 40, "requested_ref": "a" * 40}, "a" * 40),
        ({"ref": "main", "requested_ref": ""}, ""),
    ],
)
def test_legacy_automatic_pins_do_not_replace_explicit_refs(
    source: dict[str, object], expected: str
) -> None:
    assert repository_tracking_ref(source) == expected


def test_legacy_inventory_and_update_check_use_the_same_tracking_ref(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def scenario() -> None:
        source = {
            "kind": "github",
            "url": "https://github.com/example/plugin",
            "ref": "a" * 40,
            "commit": "a" * 40,
            "sha256": "a" * 64,
        }
        state = {
            "generation": 1,
            "installations": {"sample": {"source": source, "version": "1.0.0"}},
        }
        checker = AsyncMock(return_value=("b" * 64, (2, 0, 0)))
        monkeypatch.setattr(plugin_packages, "package_root", lambda: tmp_path)
        monkeypatch.setattr(plugin_packages, "read_state", lambda _root: state)
        monkeypatch.setattr(plugin_packages, "_require_admin_user_id", lambda _request: 7)
        monkeypatch.setattr(plugin_packages, "check_ready_package_release", checker)
        monkeypatch.setattr(plugin_packages, "_update_cache", {})
        inventory = await plugin_packages.admin_plugin_packages_route({})
        assert json.loads(inventory.body)["installations"]["sample"]["source"]["ref"] == ""
        response = await plugin_packages.admin_plugin_updates_route({})
        assert json.loads(response.body)["updates"] == {"sample": True}
        checker.assert_awaited_once_with(source["url"], "")
        assert source["ref"] == "a" * 40

    asyncio.run(scenario())


@pytest.mark.parametrize("commit", ["main", "a" * 39, "a" * 41])
def test_snapshot_commit_must_be_a_full_sha(commit: str) -> None:
    async def scenario() -> None:
        with pytest.raises(PluginPackageError, match="invalid_repository_commit"):
            await sources.fetch_ready_package("https://github.com/example/plugin", commit=commit)

    asyncio.run(scenario())


def test_stage_passes_snapshot_and_tracking_ref_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def scenario() -> None:
        fetcher = AsyncMock(return_value=(b"archive", {}))
        monkeypatch.setattr(
            plugin_packages,
            "_json",
            AsyncMock(
                return_value={
                    "url": "https://github.com/example/plugin",
                    "ref": "release/stable",
                    "commit": "a" * 40,
                }
            ),
        )
        monkeypatch.setattr(plugin_packages, "fetch_ready_package", fetcher)
        await plugin_packages._repository_candidate(make_mocked_request("POST", "/"), pinned=True)
        fetcher.assert_awaited_once_with(
            "https://github.com/example/plugin", "release/stable", commit="a" * 40
        )

    asyncio.run(scenario())
