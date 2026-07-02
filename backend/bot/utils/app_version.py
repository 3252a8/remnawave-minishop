"""Single source of truth for the application version string.

Resolution order mirrors the Dockerfile build chain so the dev checkout and
the runtime container agree on the value:

    REMNAWAVE_MINISHOP_VERSION env > .build-version file > live ``git describe``
    > ``dev+unknown``

Build provenance is intentionally separate from the version: official release
automation stamps official images, while local/fork builds default to custom.

The same value powers the admin sidebar (web process) and the anonymous
telemetry beacon (worker process), so "active installs" and version
breakdowns line up across both.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

# ``/app`` in the container (parent of ``/app/backend``); repo root in dev.
# Matches where the Dockerfile drops .build-version / .build-tag / .build-commit.
APP_ROOT = Path(__file__).resolve().parents[3]

_APP_VERSION_CACHE: str | None = None
_APP_BUILD_PROVENANCE_CACHE: str | None = None

BUILD_PROVENANCE_OFFICIAL = "official"
BUILD_PROVENANCE_CUSTOM = "custom"
BUILD_PROVENANCE_UNKNOWN = "unknown"
_BUILD_PROVENANCE_VALUES = {
    BUILD_PROVENANCE_OFFICIAL,
    BUILD_PROVENANCE_CUSTOM,
    BUILD_PROVENANCE_UNKNOWN,
}


def _run_git_command(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=APP_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _normalize_version_branch(raw_branch: str) -> str:
    branch = str(raw_branch or "").strip()
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if branch.startswith(prefix):
            branch = branch[len(prefix) :]
            break
    if branch in ("", "HEAD"):
        return ""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-")[:48]


def _resolve_version_branch() -> str:
    for env_name in (
        "REMNAWAVE_MINISHOP_BRANCH",
        "GIT_BRANCH",
        "BRANCH_NAME",
        "GITHUB_REF_NAME",
        "CI_COMMIT_REF_NAME",
    ):
        branch = _normalize_version_branch(os.getenv(env_name, ""))
        if branch:
            return branch
    return _normalize_version_branch(
        _run_git_command("branch", "--show-current")
        or _run_git_command("symbolic-ref", "--quiet", "--short", "HEAD")
    )


def _format_app_version(tag: str, sha: str, branch: str) -> str:
    branch_suffix = "" if not branch or branch == "main" else f"-{branch}"
    if tag and sha:
        return f"{tag}{branch_suffix}+g{sha}"
    if sha:
        return f"dev{branch_suffix}+g{sha}"
    if tag:
        return f"{tag}{branch_suffix}"
    return f"dev{branch_suffix}+unknown"


def _read_build_file(name: str) -> str:
    try:
        return (APP_ROOT / name).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _normalize_build_provenance(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if not value:
        return ""
    aliases = {
        "true": BUILD_PROVENANCE_OFFICIAL,
        "1": BUILD_PROVENANCE_OFFICIAL,
        "yes": BUILD_PROVENANCE_OFFICIAL,
        "upstream": BUILD_PROVENANCE_OFFICIAL,
        "release": BUILD_PROVENANCE_OFFICIAL,
        "false": BUILD_PROVENANCE_CUSTOM,
        "0": BUILD_PROVENANCE_CUSTOM,
        "no": BUILD_PROVENANCE_CUSTOM,
        "fork": BUILD_PROVENANCE_CUSTOM,
        "modified": BUILD_PROVENANCE_CUSTOM,
        "local": BUILD_PROVENANCE_CUSTOM,
    }
    value = aliases.get(value, value)
    if value in _BUILD_PROVENANCE_VALUES:
        return value
    return BUILD_PROVENANCE_CUSTOM


def resolve_app_version() -> str:
    """Full version string (cached), e.g. ``v3.4.6+gabc1234``."""
    global _APP_VERSION_CACHE
    if _APP_VERSION_CACHE:
        return _APP_VERSION_CACHE

    env_version = os.getenv("REMNAWAVE_MINISHOP_VERSION", "").strip()
    if env_version:
        _APP_VERSION_CACHE = env_version
        return env_version

    build_version = _read_build_file(".build-version")
    if build_version:
        _APP_VERSION_CACHE = build_version
        return build_version

    tag = _run_git_command("describe", "--tags", "--abbrev=0")
    sha = _run_git_command("rev-parse", "--short", "HEAD")
    branch = _resolve_version_branch()
    version = _format_app_version(tag, sha, branch)
    _APP_VERSION_CACHE = version
    return version


def resolve_app_version_tag() -> str:
    """Clean release tag for low-cardinality breakdowns, e.g. ``v3.4.6``.

    Prefers the build-time ``.build-tag`` artifact, then a live ``git
    describe``; falls back to the full version string when no tag is known.
    """
    build_tag = _read_build_file(".build-tag")
    if build_tag and build_tag != "unknown":
        return build_tag
    tag = _run_git_command("describe", "--tags", "--abbrev=0")
    if tag:
        return tag
    return resolve_app_version()


def resolve_build_provenance() -> str:
    """Low-cardinality image provenance: ``official``, ``custom`` or ``unknown``."""
    global _APP_BUILD_PROVENANCE_CACHE
    if _APP_BUILD_PROVENANCE_CACHE:
        return _APP_BUILD_PROVENANCE_CACHE

    env_value = _normalize_build_provenance(os.getenv("REMNAWAVE_MINISHOP_BUILD_PROVENANCE", ""))
    if env_value:
        _APP_BUILD_PROVENANCE_CACHE = env_value
        return env_value

    build_value = _normalize_build_provenance(_read_build_file(".build-provenance"))
    if build_value:
        _APP_BUILD_PROVENANCE_CACHE = build_value
        return build_value

    _APP_BUILD_PROVENANCE_CACHE = BUILD_PROVENANCE_CUSTOM
    return _APP_BUILD_PROVENANCE_CACHE


def resolve_image_modified() -> bool:
    """True for non-official builds, including forks and local rebuilds."""
    return resolve_build_provenance() != BUILD_PROVENANCE_OFFICIAL
