"""Bounded public repository importer for already-built plugin archives.

Repository source is metadata only. The server never runs a repository build,
hook, installer, or package manager. The package signature remains decisive.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import socket
from pathlib import PurePosixPath
from urllib.parse import quote, urlsplit

from aiohttp import ClientError, ClientSession, ClientTimeout, DummyCookieJar, TCPConnector
from aiohttp.abc import ResolveResult
from aiohttp.resolver import ThreadedResolver

from .packages import MAX_ARCHIVE_BYTES, PluginPackageError

_HOSTS = frozenset({"api.github.com", "raw.githubusercontent.com", "github.com", "gitlab.com"})
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PART = re.compile(r"^[A-Za-z0-9._-]+$")


class _PublicResolver(ThreadedResolver):
    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await super().resolve(host, port, family)
        for result in results:
            address = ipaddress.ip_address(result["host"])
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or getattr(address, "ipv4_mapped", None) is not None
            ):
                raise PluginPackageError("repository_address_blocked")
        return results


def _safe_url(value: str) -> None:
    try:
        parts = urlsplit(value)
        if (
            parts.scheme != "https"
            or parts.hostname not in _HOSTS
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or parts.fragment
        ):
            raise ValueError
    except ValueError as exc:
        raise PluginPackageError("invalid_repository_url") from exc


def _repository(value: str) -> tuple[str, str]:
    _safe_url(value)
    parts = urlsplit(value)
    if parts.query or parts.hostname not in {"github.com", "gitlab.com"}:
        raise PluginPackageError("invalid_repository_url")
    segments = [segment for segment in parts.path.strip("/").split("/") if segment]
    if len(segments) < 2 or any(not _PART.fullmatch(segment) for segment in segments):
        raise PluginPackageError("invalid_repository_url")
    if parts.hostname == "github.com" and len(segments) != 2:
        raise PluginPackageError("invalid_repository_url")
    return parts.hostname or "", "/".join(segments).removesuffix(".git")


async def _download(session: ClientSession, url: str, limit: int) -> bytes:
    _safe_url(url)
    async with session.get(url, allow_redirects=False) as response:
        if response.status in {301, 302, 303, 307, 308}:
            raise PluginPackageError("repository_redirect_blocked", status=502)
        if response.status == 404:
            raise PluginPackageError("built_package_required", status=404)
        if response.status in {403, 429}:
            raise PluginPackageError("repository_rate_limited", status=429)
        if response.status != 200:
            raise PluginPackageError("repository_unavailable", status=502)
        if response.content_length is not None and response.content_length > limit:
            raise PluginPackageError("archive_too_large", status=413)
        body = bytearray()
        async for chunk in response.content.iter_chunked(65536):
            body.extend(chunk)
            if len(body) > limit:
                raise PluginPackageError("archive_too_large", status=413)
        return bytes(body)


async def _json(session: ClientSession, url: str) -> dict[str, object]:
    try:
        value = json.loads(await _download(session, url, 1024 * 1024))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise PluginPackageError("invalid_repository_metadata", status=502) from exc
    if not isinstance(value, dict):
        raise PluginPackageError("invalid_repository_metadata", status=502)
    return value


async def fetch_ready_package(url: str, ref: str = "") -> tuple[bytes, dict[str, str]]:
    """Resolve a public ref to a commit, then fetch its ready artifact index."""
    host, project = _repository(url)
    if len(ref) > 160 or any(char in ref for char in "\\\r\n?&#"):
        raise PluginPackageError("invalid_repository_ref")
    connector = TCPConnector(resolver=_PublicResolver(), ttl_dns_cache=0, limit=2)
    try:
        async with ClientSession(
            connector=connector,
            timeout=ClientTimeout(total=120, sock_read=30),
            headers={"User-Agent": "Minishop-Plugin-Installer", "Accept-Encoding": "identity"},
            cookie_jar=DummyCookieJar(),
            trust_env=False,
            auto_decompress=False,
        ) as session:
            if host == "github.com":
                base = f"https://api.github.com/repos/{quote(project, safe='/')}"
                chosen_ref = ref or str((await _json(session, base)).get("default_branch") or "")
                commit = str(
                    (await _json(session, f"{base}/commits/{quote(chosen_ref, safe='')}")).get(
                        "sha"
                    )
                    or ""
                )
                if not _SHA.fullmatch(commit):
                    raise PluginPackageError("invalid_repository_commit", status=502)
                raw = f"https://raw.githubusercontent.com/{project}/{commit}"
                index = await _json(session, f"{raw}/minishop-plugin.json")
                artifact_url_base = raw
            else:
                base = f"https://gitlab.com/api/v4/projects/{quote(project, safe='')}"
                chosen_ref = ref or str((await _json(session, base)).get("default_branch") or "")
                commit = str(
                    (
                        await _json(
                            session, f"{base}/repository/commits/{quote(chosen_ref, safe='')}"
                        )
                    ).get("id")
                    or ""
                )
                if not _SHA.fullmatch(commit):
                    raise PluginPackageError("invalid_repository_commit", status=502)
                index = await _json(
                    session,
                    f"{base}/repository/files/minishop-plugin.json/raw?ref={commit}",
                )
                artifact_url_base = f"{base}/repository/files"
            artifact = index.get("artifact")
            digest = index.get("sha256")
            if (
                index.get("schema_version") != 1
                or not isinstance(artifact, str)
                or not isinstance(digest, str)
                or not _DIGEST.fullmatch(digest)
            ):
                raise PluginPackageError("invalid_repository_index")
            path = PurePosixPath(artifact)
            if (
                path.is_absolute()
                or path.suffix.lower() != ".zip"
                or not artifact
                or len(artifact) > 220
                or any(not _PART.fullmatch(part) or part in {".", ".."} for part in path.parts)
            ):
                raise PluginPackageError("invalid_repository_index")
            if host == "github.com":
                artifact_url = f"{artifact_url_base}/{quote(artifact, safe='/')}"
            else:
                artifact_url = f"{artifact_url_base}/{quote(artifact, safe='')}/raw?ref={commit}"
            body = await _download(session, artifact_url, MAX_ARCHIVE_BYTES)
            if hashlib.sha256(body).hexdigest() != digest:
                raise PluginPackageError("repository_artifact_hash_mismatch")
            return body, {
                "kind": "github" if host == "github.com" else "gitlab",
                "url": f"https://{host}/{project}",
                "ref": chosen_ref,
                "commit": commit,
                "artifact": artifact,
                "sha256": digest,
            }
    except (ClientError, TimeoutError, OSError) as exc:
        raise PluginPackageError("repository_unavailable", status=502) from exc
