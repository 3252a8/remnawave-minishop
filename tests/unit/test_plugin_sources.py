"""Public repository inputs stay inside the ready-artifact boundary."""

from __future__ import annotations

import pytest

from bot.plugins.packages import PluginPackageError
from bot.plugins.sources import _repository, _safe_url, release_version


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
