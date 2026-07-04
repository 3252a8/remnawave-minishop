"""Test fixtures that isolate the suite from the developer's local .env.

Provider configs now declare their own ``BaseSettings`` with ``env_file=".env"``,
so a developer who runs ``pytest`` from a project that has real credentials in
``.env`` would otherwise see provider services try to connect (e.g. CryptoPay
spinning up an aiohttp session in __init__).

We set ``PROVIDER_ENV_FILE=""`` (consumed by each provider's
``ProviderEnvConfig.model_config["env_file"]`` factory) and strip real
provider env vars from the test process.
"""

from __future__ import annotations

import os

import pytest


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
                "BEPUSDT_",
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
                "PAYMENT_BEPUSDT_",
                "PAYMENT_PALLY_",
                "PAYMENT_CRYPTOPAY_",
                "PAYMENT_YOOKASSA_",
                "PAYMENT_CLOUDPAYMENTS_",
                "PAYMENT_STRIPE_",
                "PAYMENT_STARS_",
            )
        ):
            monkeypatch.delenv(key, raising=False)
