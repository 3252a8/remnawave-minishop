"""Test fixtures that isolate the suite from the developer's environment.

Provider configs now declare their own ``BaseSettings`` with ``env_file=".env"``,
so a developer who runs ``pytest`` from a project that has real credentials in
``.env`` would otherwise see provider services try to connect (e.g. CryptoPay
spinning up an aiohttp session in __init__).

We set ``PROVIDER_ENV_FILE=""`` (consumed by each provider's
``ProviderEnvConfig.model_config["env_file"]`` factory) and strip real
provider env vars from the test process.

The active Python interpreter can also contain private or third-party packages
that publish ``minishop.plugins`` entry points. Core tests must be deterministic
regardless of those globally installed extensions, so discovery is empty by
default for the whole test session. Loader tests override the isolated seam when
they exercise production entry-point discovery explicitly.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture
def symlink_support(tmp_path: Path) -> None:
    link = tmp_path / "symlink-probe"
    try:
        link.symlink_to(tmp_path / "symlink-target")
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    else:
        link.unlink()


@pytest.fixture(scope="session", autouse=True)
def _isolate_external_plugin_entry_points():
    from bot.plugins import loader as plugins_loader

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(plugins_loader, "_plugin_entry_points", lambda: ())
    plugins_loader.reset_plugins()
    yield
    plugins_loader.reset_plugins()
    monkeypatch.undo()


def _provider_env_prefixes() -> tuple[str, ...]:
    """Env prefixes every registered provider reads, derived from the registry.

    A hand-written list silently misses the next provider: Tribute was added
    with a ``TRIBUTE_SHOP_ENABLED`` cross-field rule, and a developer with that
    variable exported saw unrelated suites fail. Reading the prefixes off the
    provider models keeps isolation complete by construction.
    """

    from bot.payment_providers import iter_provider_specs

    prefixes: set[str] = set()
    for spec in iter_provider_specs():
        for model_class in (spec.config_class, spec.presentation_class):
            if model_class is None:
                continue
            prefix = str(model_class.model_config.get("env_prefix") or "").strip()
            if prefix:
                prefixes.add(prefix)
    return tuple(sorted(prefixes))


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_ENV_FILE", "")
    prefixes = _provider_env_prefixes()
    for key in list(os.environ.keys()):
        if any(key.startswith(prefix) for prefix in prefixes):
            monkeypatch.delenv(key, raising=False)
