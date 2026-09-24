import asyncio
import copy
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

from bot.app.web.webapp import extension_runtime
from bot.app.web.webapp.extension_payments import balance_available, payment_methods
from bot.app.web.webapp.guide_document import remnawave_v1_to_guide_document
from bot.payment_providers.base import PaymentProviderSpec
from bot.plugins.extensions import (
    ExtensionContributions,
    ExtensionError,
    GuideContribution,
    GuideProvider,
    ProductQuote,
    ResourceProvider,
    ResourceResult,
    UserContext,
)
from bot.plugins.extensions.guides import merge_guides
from bot.plugins.extensions.registry import ExtensionRegistry, set_registry
from config.subscription_guides_config import default_subscription_guides_config_text


@pytest.fixture(autouse=True)
def registry():
    value = ExtensionRegistry()
    set_registry(value)
    yield value
    set_registry(ExtensionRegistry())


@asynccontextmanager
async def context(_request):
    yield UserContext(SimpleNamespace(), 42, "ru")


def test_router_platform_is_merged_beside_existing_platforms(registry):
    base = json.loads(default_subscription_guides_config_text())
    fragment = copy.deepcopy(base)
    router = copy.deepcopy(base["platforms"]["windows"])
    router["displayName"].update({"ru": "Роутеры", "en": "Routers"})
    fragment["platforms"] = {"routers": router}
    provider = GuideProvider("install", AsyncMock(return_value=GuideContribution(fragment)))
    registry.register("devices", "1", ExtensionContributions(guides=(provider,)))
    with patch("bot.plugins.extensions.guides.preferences", AsyncMock(return_value={})):
        merged = asyncio.run(merge_guides(UserContext(SimpleNamespace(), 42, "ru"), base))
    assert merged["platforms"]["ios"] == base["platforms"]["ios"]
    assert merged["platforms"]["android"] == base["platforms"]["android"]
    assert merged["platforms"]["windows"] == base["platforms"]["windows"]
    assert "devices--install--routers" in merged["platforms"]
    document = remnawave_v1_to_guide_document(merged)
    inserted = next(
        item for item in document["platforms"] if item["id"] == "devices--install--routers"
    )
    assert inserted["displayName"]["ru"] == "Роутеры"
    assert inserted["apps"]
    assert "routers" not in base["platforms"]
    with patch(
        "bot.plugins.extensions.guides.preferences",
        AsyncMock(return_value={"guide:install": (True, -1)}),
    ):
        reordered = asyncio.run(merge_guides(UserContext(SimpleNamespace(), 42, "ru"), base))
    assert next(iter(reordered["platforms"])) == "devices--install--routers"


def test_hidden_guide_does_not_call_provider(registry):
    resolve = AsyncMock()
    registry.register(
        "devices", "1", ExtensionContributions(guides=(GuideProvider("install", resolve),))
    )
    with patch(
        "bot.plugins.extensions.guides.preferences",
        AsyncMock(return_value={"guide:install": (False, 1)}),
    ):
        assert asyncio.run(merge_guides(UserContext(SimpleNamespace(), 42, "en"), None)) is None
    resolve.assert_not_awaited()


def test_changed_generation_hides_old_guides_without_calling_provider(registry):
    resolve = AsyncMock()
    registry.register(
        "devices", "1", ExtensionContributions(guides=(GuideProvider("install", resolve),))
    )
    base = json.loads(default_subscription_guides_config_text())
    with patch("bot.plugins.extensions.guides.generation_is_current", return_value=False):
        assert asyncio.run(merge_guides(UserContext(SimpleNamespace(), 42, "en"), base)) == base
    resolve.assert_not_awaited()


def test_customer_assets_cannot_expose_administrative_bundle(registry, tmp_path):
    registry.register("devices", "1", ExtensionContributions())
    digest = "a" * 64
    release = tmp_path / "releases/devices" / digest
    (release / "frontend").mkdir(parents=True)
    data = b"export const customer = true;"
    (release / "frontend/customer.js").write_bytes(data)
    (release / "plugin.json").write_text(
        json.dumps(
            {
                "frontend": {"entry": "admin.js", "user": {"entry": "customer.js"}},
                "files": {
                    "frontend/customer.js": hashlib.sha256(data).hexdigest(),
                    "frontend/admin.js": "private",
                },
            }
        ),
        encoding="utf-8",
    )
    state = {"installations": {"devices": {"enabled": True, "digest": digest}}}
    request = SimpleNamespace(match_info={"owner": "devices", "digest": digest, "path": "admin.js"})
    with (
        patch.object(extension_runtime, "user_context", context),
        patch.object(extension_runtime, "package_root", return_value=tmp_path),
        patch.object(extension_runtime, "read_state", return_value=state),
    ):
        with pytest.raises(web.HTTPNotFound):
            asyncio.run(extension_runtime.extension_asset_route(request))
        request.match_info["path"] = "customer.js"
        response = asyncio.run(extension_runtime.extension_asset_route(request))
        assert response.body == data
        assert "no-store" in response.headers["Cache-Control"]
        (release / "frontend/customer.js").write_bytes(b"tampered")
        with pytest.raises(web.HTTPServiceUnavailable):
            asyncio.run(extension_runtime.extension_asset_route(request))


def test_resource_uses_server_identity_and_never_caches_private_data(registry):
    async def resolve(user, key):
        assert user.user_id == 42
        if key != "mine":
            raise ExtensionError("resource_not_found", 404)
        return ResourceResult(b"private-key", "text/plain", "router.conf")

    registry.register(
        "devices", "1", ExtensionContributions(resources=(ResourceProvider("config", resolve),))
    )
    with patch.object(extension_runtime, "user_context", context):
        request = SimpleNamespace(query={"provider": "devices:config", "key": "someone-else"})
        assert asyncio.run(extension_runtime.extension_resource_route(request)).status == 404
        request.query["key"] = "mine"
        response = asyncio.run(extension_runtime.extension_resource_route(request))
        assert response.body == b"private-key"
        assert "no-store" in response.headers["Cache-Control"]
        assert "attachment" in response.headers["Content-Disposition"]


def test_runtime_requires_authentication_before_discovery():
    with (
        patch.object(extension_runtime, "_require_user_id", side_effect=web.HTTPUnauthorized),
        pytest.raises(web.HTTPUnauthorized),
    ):
        asyncio.run(extension_runtime.extension_runtime_route(SimpleNamespace()))


@pytest.mark.parametrize("currency,expected", [("RUB", ["card"]), ("XTR", ["stars"]), ("EUR", [])])
def test_checkout_never_converts_frozen_price_or_uses_subscription_catalog(currency, expected):
    quote = ProductQuote(
        title="Device setup",
        amount_minor=50000,
        currency=currency,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    card = PaymentProviderSpec(
        id="card",
        provider_key="card",
        label="Card",
        pending_status="pending",
        enabled=lambda _: True,
        create_webapp_payment=AsyncMock(),
        payment_amount_resolver=lambda _settings, _currency, amount: Decimal(amount) >= 100,
    )
    providers = [
        card,
        replace(card, id="stars", price_source="stars"),
        replace(card, id="recurring", manages_recurring=True),
        replace(card, id="catalog", price_managed_externally=True),
        replace(card, id="disabled", enabled=lambda _: False),
        replace(card, id="minimum", payment_amount_resolver=lambda *_: False),
        replace(card, id="context", payment_context_resolver=lambda *_: False),
    ]
    with patch("bot.app.web.webapp.extension_payments.iter_provider_specs", return_value=providers):
        assert [
            item.id
            for item in payment_methods(
                SimpleNamespace(),
                web.Application(),
                is_admin=False,
                quote=quote,
                order_id="a" * 32,
            )
        ] == expected


@pytest.mark.parametrize(
    "enabled,currency,expected", [(True, "RUB", True), (False, "RUB", False), (True, "XTR", False)]
)
def test_balance_checkout_requires_enabled_matching_currency(enabled, currency, expected):
    settings = SimpleNamespace(USER_BALANCE_ENABLED=enabled, USER_BALANCE_CURRENCY="RUB")
    quote = ProductQuote(
        title="Device setup",
        amount_minor=100,
        currency=currency,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    with patch("bot.app.web.webapp.extension_payments.get_settings", return_value=settings):
        assert balance_available(SimpleNamespace(), quote) is expected
