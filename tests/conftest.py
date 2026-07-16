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

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolate_external_plugin_entry_points():
    from bot.plugins import loader as plugins_loader

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(plugins_loader, "_plugin_entry_points", lambda: ())
    plugins_loader.reset_plugins()
    yield
    plugins_loader.reset_plugins()
    monkeypatch.undo()


@pytest.fixture(autouse=True)
def _isolate_provider_env(monkeypatch):
    monkeypatch.setenv("PROVIDER_ENV_FILE", "")
    for key in list(os.environ.keys()):
        if any(
            key.startswith(prefix)
            for prefix in (
                "FREEKASSA_",
                "PLATEGA_",
                "SEVERPAY_",
                "WATA_",
                "HELEKET_",
                "LAVA_",
                "PALLY_",
                "CRYPTOPAY_",
                "YOOKASSA_",
                "CLOUDPAYMENTS_",
                "STRIPE_",
                "PAYMENT_FREEKASSA_",
                "PAYMENT_PLATEGA_",
                "PAYMENT_SEVERPAY_",
                "PAYMENT_WATA_",
                "PAYMENT_HELEKET_",
                "PAYMENT_LAVA_",
                "PAYMENT_PALLY_",
                "PAYMENT_CRYPTOPAY_",
                "PAYMENT_YOOKASSA_",
                "PAYMENT_CLOUDPAYMENTS_",
                "PAYMENT_STRIPE_",
                "PAYMENT_STARS_",
            )
        ):
            monkeypatch.delenv(key, raising=False)
