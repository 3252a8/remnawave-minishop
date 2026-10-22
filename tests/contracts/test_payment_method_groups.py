"""Fallback metadata describes the funding instrument and shared gateway."""

import pytest
from aiohttp import web

from bot.app.web.webapp.serializers_billing_options import _serialize_payment_methods
from bot.payment_providers import get_provider_spec, registry
from bot.payment_providers.base import PaymentMethodGroup, PaymentProviderSpec
from config.settings import Settings


@pytest.mark.parametrize(
    ("method", "group", "provider"),
    [
        ("wata", "fiat", "wata_service"),
        ("wata_subscription", "fiat", "wata_service"),
        ("wata_crypto", "crypto", "wata_service"),
        ("platega_sbp", "fiat", "platega_service"),
        ("platega_card", "fiat", "platega_service"),
        ("platega_crypto", "crypto", "platega_service"),
        ("platega_all_methods", "mixed", "platega_service"),
        ("rollypay_crypto", "crypto", "rollypay_service"),
        ("rollypay", "mixed", "rollypay_service"),
        ("cryptopay", "crypto", "cryptopay_service"),
        ("cryptomus", "crypto", "cryptomus_service"),
        ("paykilla", "crypto", "paykilla_service"),
        ("stars", "stars", "stars_service"),
    ],
)
def test_funding_group_is_independent_of_invoice_currency(
    method: str, group: PaymentMethodGroup, provider: str
) -> None:
    spec = get_provider_spec(method)
    assert spec is not None
    assert spec.payment_group == group
    assert spec.provider_id == provider


def test_webapp_serializes_explicit_groups_without_guessing_unknown_plugins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    examples: tuple[tuple[str, PaymentMethodGroup | None], ...] = (
        ("custom_crypto", "crypto"),
        ("custom_unknown", None),
    )
    specs = tuple(
        PaymentProviderSpec(
            id=method,
            provider_key=method,
            service_key="test_gateway",
            label=method,
            pending_status="pending",
            enabled=lambda _: True,
            requires_configured_service=False,
            payment_group=group,
        )
        for method, group in examples
    )
    monkeypatch.setattr(registry, "PAYMENT_PROVIDER_SPECS", specs)
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="test",
        POSTGRES_PASSWORD="test",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        DEFAULT_CURRENCY_SYMBOL="RUB",
        PAYMENT_METHODS_ORDER="custom_crypto,custom_unknown",
    )

    methods = _serialize_payment_methods(settings, web.Application(), "en")

    assert [(m["id"], m["group"], m["provider_id"]) for m in methods] == [
        ("custom_crypto", "crypto", "test_gateway"),
        ("custom_unknown", None, "test_gateway"),
    ]
