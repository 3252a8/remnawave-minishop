"""Repository resolution and bounded network handling without external traffic."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver

from config.theme_packages import providers
from config.theme_packages.models import MAX_ARCHIVE, PackageError, RepositoryRequest

COMMIT = "a" * 40


@pytest.mark.parametrize(
    ("repository", "project_url", "ref", "subdir", "kind"),
    [
        (
            RepositoryRequest(url="https://github.com/author/themes.git"),
            "https://api.github.com/repos/author/themes",
            "main",
            "",
            "github",
        ),
        (
            RepositoryRequest(url="https://github.com/author/themes", ref="v1.2.0", subdir="packs"),
            "https://api.github.com/repos/author/themes",
            "v1.2.0",
            "packs",
            "github",
        ),
        (
            RepositoryRequest(
                url="https://gitlab.com/group/subgroup/themes/-/tree/feature/new/packs"
            ),
            "https://gitlab.com/api/v4/projects/group%2Fsubgroup%2Fthemes",
            "feature/new",
            "packs",
            "gitlab",
        ),
    ],
)
def test_repository_resolves_ref_and_downloads_pinned_commit(
    monkeypatch: pytest.MonkeyPatch,
    repository: RepositoryRequest,
    project_url: str,
    ref: str,
    subdir: str,
    kind: str,
) -> None:
    client = MagicMock(spec=ClientSession)
    client.__aenter__.return_value = client
    monkeypatch.setattr(providers, "ClientSession", MagicMock(return_value=client))
    monkeypatch.setattr(providers, "TCPConnector", MagicMock())
    monkeypatch.setattr(providers, "PublicResolver", MagicMock())
    calls: list[str] = []

    async def info(_session: ClientSession, url: str) -> dict[str, object]:
        calls.append(url)
        if url == project_url:
            return {"default_branch": "main"}
        if url.endswith("feature%2Fnew%2Fpacks"):
            raise PackageError("repository_not_found", status=404)
        assert url.endswith(providers.quote(ref, safe=""))
        return {"sha" if kind == "github" else "id": COMMIT}

    fetch = AsyncMock(return_value=b"archive")
    monkeypatch.setattr(providers, "metadata", info)
    monkeypatch.setattr(providers, "download", fetch)
    body, source = asyncio.run(providers.fetch_repository(repository))
    assert body == b"archive"
    assert (source.kind, source.ref, source.subdir, source.commit) == (kind, ref, subdir, COMMIT)
    expected = project_url + ("/zipball/" if kind == "github" else "/repository/archive.zip?sha=")
    fetch.assert_awaited_once_with(client, expected + COMMIT, limit=MAX_ARCHIVE)
    assert calls[0] == project_url


@pytest.mark.parametrize(
    ("tree", "commit", "error"),
    [
        ("", "../unsafe", "invalid_repository_commit"),
        ("/tree/other/themes", COMMIT, "repository_ref_ambiguous"),
    ],
)
def test_repository_rejects_ambiguous_ref_and_invalid_commit(
    monkeypatch: pytest.MonkeyPatch,
    tree: str,
    commit: str,
    error: str,
) -> None:
    client = MagicMock(spec=ClientSession)
    monkeypatch.setattr(providers, "ClientSession", MagicMock(return_value=client))
    monkeypatch.setattr(providers, "TCPConnector", MagicMock())
    monkeypatch.setattr(providers, "PublicResolver", MagicMock())
    monkeypatch.setattr(providers, "metadata", AsyncMock(return_value={"sha": commit}))
    fetch = AsyncMock()
    monkeypatch.setattr(providers, "download", fetch)
    with pytest.raises(PackageError, match=error):
        asyncio.run(
            providers.fetch_repository(
                RepositoryRequest(url="https://github.com/author/themes" + tree, ref="main")
            )
        )
    fetch.assert_not_awaited()


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "224.0.0.1", "::ffff:8.8.8.8"]
)
def test_dns_rebinding_to_nonpublic_address_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    address: str,
) -> None:
    result: ResolveResult = {
        "hostname": "github.com",
        "host": address,
        "port": 443,
        "family": socket.AF_INET,
        "proto": 0,
        "flags": 0,
    }
    monkeypatch.setattr(ThreadedResolver, "resolve", AsyncMock(return_value=[result]))

    async def scenario() -> None:
        resolver = providers.PublicResolver()
        try:
            with pytest.raises(PackageError, match="repository_address_blocked"):
                await resolver.resolve("github.com", 443)
        finally:
            await resolver.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("status", "location", "body", "error"),
    [
        (302, "http://127.0.0.1/private", b"", "invalid_repository_url"),
        (429, "", b"", "repository_rate_limited"),
        (200, "", b"12345", "archive_too_large"),
    ],
)
def test_download_rejects_redirects_rate_limits_and_stream_overflow(
    status: int,
    location: str,
    body: bytes,
    error: str,
) -> None:
    async def chunks(_size: int) -> AsyncIterator[bytes]:
        yield body[:2]
        yield body[2:]

    response = MagicMock()
    response.status = status
    response.headers = {"Location": location}
    response.content_length = None
    response.content.iter_chunked = chunks
    response.__aenter__.return_value = response
    client = MagicMock(spec=ClientSession)
    client.get.return_value = response
    with pytest.raises(PackageError, match=error):
        asyncio.run(providers.download(client, "https://github.com/a/b", limit=4))
    client.get.assert_called_once_with("https://github.com/a/b", allow_redirects=False)
