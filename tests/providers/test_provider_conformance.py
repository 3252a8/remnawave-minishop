"""Conformance tests for the payment-provider contract.

These lock the uniform provider surface so a new or changed provider that drifts
fails CI ("tooling, not agreement"). Two kinds of checks:

1. Structural invariants every registered provider must satisfy.
2. The link-flow contract: a provider either drives the shared engine via a
   module-level ``_DESCRIPTOR`` (``bot.payment_providers.shared.link_flow``), or
   it is explicitly allow-listed below as *bespoke* with a reason explaining the
   genuine divergence that makes the uniform engine a behavior change.

Keep ``LINKFLOW_BESPOKE`` honest: a new provider should use the shared engine
unless it truly cannot, and the reason should name the divergence.
"""

from __future__ import annotations

import importlib

import pytest

from bot.payment_providers.base import BaseProviderService
from bot.payment_providers.registry import PAYMENT_PROVIDER_SPECS
from bot.payment_providers.shared.http_client import HttpClientMixin
from bot.payment_providers.shared.link_flow import LinkPaymentDescriptor

SPECS = list(PAYMENT_PROVIDER_SPECS)
SPEC_IDS = [spec.id for spec in SPECS]

# Provider package names (one package per service). ``provider_key`` may repeat
# across sub-variants (platega_sbp / platega_crypto), so the package set is
# derived from ``service_key`` instead.
PROVIDER_NAMES = sorted({s.service_key.removesuffix("_service") for s in SPECS if s.service_key})

# Providers whose callback/webapp flow is genuinely provider-specific and does
# NOT use the shared link-flow engine. Each value documents the divergence.
LINKFLOW_BESPOKE = {
    "cloudpayments": "answers the callback query mid-flow (safe_callback_answer)",
    "cryptopay": "aiocryptopay invoice flow, not a hosted-link redirect",
    "freekassa": "callback builds a localized order-info lead_text",
    "pally": "answers the callback query mid-flow + per-flow create_bill args",
    "paykilla": "bespoke invoice flow not unified with the shared engine",
    "platega": "sbp/crypto sub-variants, each with its own SPEC and variant routing",
    "stars": "Telegram Stars in-app invoice; no external payment link or webhook",
    "stripe": "card PaymentIntent / saved-card recurring, not a hosted-link redirect",
    "wata": "multi-profile terminal routing with per-profile signature",
    "yookassa": "HWID variants + saved-card autopayments",
}


# Webhook handling is NOT one base-class contract (F2 audit). Each provider is
# classified into exactly one profile, derived below from the real service class
# and SPEC so the inventory cannot silently drift:
#
#   base-template        — inherits BaseProviderService (parse -> verify -> handle).
#   service-route        — HttpClientMixin service owns its own ``webhook_route``
#                          (IP allowlists, multi-scheme signatures, idempotency).
#   standalone-sdk-route — has a webhook route but neither base class (SDK objects
#                          + IP allowlist, e.g. yookassa).
#   telegram-invoice     — no provider HTTP webhook at all (Telegram Stars).
#
# The detection (`_detect_webhook_profile`) and the partition test below keep this
# map honest: changing a service's base class, or adding/removing a webhook route,
# fails CI until this inventory is updated to match.
WEBHOOK_PROFILES = {
    "base-template": {"cryptopay"},
    "service-route": {
        "cloudpayments",
        "freekassa",
        "heleket",
        "lava",
        "pally",
        "paykilla",
        "platega",
        "severpay",
        "stripe",
        "wata",
    },
    "standalone-sdk-route": {"yookassa"},
    "telegram-invoice": {"stars"},
}


# A provider package ``__init__`` is a public facade, not an implementation
# barrel. These stdlib / framework / typing names leak in when a facade re-exports
# its whole service module; F4 trimmed every facade and this set keeps them out.
BANNED_FACADE_EXPORTS = frozenset(
    {
        # stdlib
        "asyncio",
        "base64",
        "cast",
        "datetime",
        "hashlib",
        "hmac",
        "json",
        "logging",
        "time",
        "parse_qsl",
        "unquote_plus",
        # aiohttp / aiogram / sqlalchemy / pydantic / sdk framework
        "web",
        "types",
        "F",
        "Router",
        "Bot",
        "AsyncSession",
        "sessionmaker",
        "Field",
        "field_validator",
        "SettingsConfigDict",
        "Update",
        "Networks",
        "AioCryptoPay",
        "InlineKeyboardButton",
        "InlineKeyboardMarkup",
        "LabeledPrice",
        # typing
        "Any",
        "Optional",
        "Dict",
        "Tuple",
        "List",
        "Mapping",
        "Sequence",
        # third-party misc
        "InvalidOperation",
    }
)


def _service_module(name: str):
    return importlib.import_module(f"bot.payment_providers.{name}.service")


def _service_class(name: str) -> type:
    """Return the single ``*Service`` class defined in a provider's service module."""
    module = _service_module(name)
    classes = [
        obj
        for attr, obj in vars(module).items()
        if isinstance(obj, type) and obj.__module__ == module.__name__ and attr.endswith("Service")
    ]
    assert len(classes) == 1, f"{name}: expected exactly one *Service class, found {classes}"
    return classes[0]


def _specs_for(name: str) -> list:
    return [s for s in SPECS if s.service_key and s.service_key.removesuffix("_service") == name]


def _provider_has_webhook(name: str) -> bool:
    return any(spec.webhook_route is not None for spec in _specs_for(name))


def _detect_webhook_profile(name: str) -> str:
    service_class = _service_class(name)
    if issubclass(service_class, BaseProviderService):
        return "base-template"
    if not _provider_has_webhook(name):
        return "telegram-invoice"
    if issubclass(service_class, HttpClientMixin):
        return "service-route"
    return "standalone-sdk-route"


def _declared_webhook_profile(name: str) -> str | None:
    for profile, members in WEBHOOK_PROFILES.items():
        if name in members:
            return profile
    return None


@pytest.mark.parametrize("spec", SPECS, ids=SPEC_IDS)
def test_spec_identity_present(spec):
    assert spec.id, "provider spec must declare a non-empty id"
    assert spec.provider_key, f"{spec.id}: provider_key must be non-empty"
    assert spec.create_webapp_payment is not None, f"{spec.id}: create_webapp_payment missing"


def test_spec_ids_unique():
    assert len(SPEC_IDS) == len(set(SPEC_IDS)), f"duplicate provider spec ids: {SPEC_IDS}"


def test_each_service_key_has_a_creator():
    # Sub-variant specs (platega_crypto, wata_crypto) reuse the parent spec's
    # service, so create_service is per service_key, not per spec.
    creators: dict[str, bool] = {}
    for spec in SPECS:
        if not spec.service_key:
            continue
        creators[spec.service_key] = creators.get(spec.service_key, False) or (
            spec.create_service is not None
        )
    missing = [key for key, has in creators.items() if not has]
    assert not missing, f"service keys with no create_service among their specs: {missing}"


def test_webhook_paths_unique_where_declared():
    paths = []
    for spec in SPECS:
        if spec.webhook_route is None or spec.webhook_path is None:
            continue
        try:
            path = spec.webhook_path(None)
        except Exception:  # pragma: no cover - source-dependent path getters
            continue
        if path:
            paths.append(path)
    assert len(paths) == len(set(paths)), f"duplicate webhook paths: {paths}"


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_provider_uses_engine_or_is_allowlisted(name):
    descriptor = getattr(_service_module(name), "_DESCRIPTOR", None)
    if descriptor is not None:
        assert isinstance(descriptor, LinkPaymentDescriptor)
        assert name not in LINKFLOW_BESPOKE, (
            f"{name} defines a link-flow _DESCRIPTOR but is also in LINKFLOW_BESPOKE; "
            f"remove it from the bespoke allowlist"
        )
    else:
        assert name in LINKFLOW_BESPOKE, (
            f"{name} neither defines a link-flow _DESCRIPTOR nor is allow-listed as bespoke. "
            f"Drive it through bot.payment_providers.shared.link_flow, or add a documented "
            f"exemption to LINKFLOW_BESPOKE explaining the divergence."
        )


def test_bespoke_allowlist_has_no_stale_entries():
    unknown = set(LINKFLOW_BESPOKE) - set(PROVIDER_NAMES)
    assert not unknown, f"LINKFLOW_BESPOKE names that are not real providers: {sorted(unknown)}"


@pytest.mark.parametrize("name", [n for n in PROVIDER_NAMES if n not in LINKFLOW_BESPOKE])
def test_descriptor_is_consistent_with_spec(name):
    descriptor = getattr(_service_module(name), "_DESCRIPTOR")
    assert descriptor.provider_key == descriptor.spec.provider_key, (
        f"{name}: descriptor.provider_key ({descriptor.provider_key}) != "
        f"spec.provider_key ({descriptor.spec.provider_key})"
    )
    assert descriptor.pending_status == descriptor.spec.pending_status, (
        f"{name}: descriptor.pending_status ({descriptor.pending_status}) != "
        f"spec.pending_status ({descriptor.spec.pending_status})"
    )
    assert descriptor.service_app_key == descriptor.spec.service_key, (
        f"{name}: descriptor.service_app_key ({descriptor.service_app_key}) != "
        f"spec.service_key ({descriptor.spec.service_key})"
    )


def test_webhook_profiles_partition_providers():
    members = [name for names in WEBHOOK_PROFILES.values() for name in names]
    assert len(members) == len(set(members)), (
        f"a provider appears in more than one webhook profile: {sorted(members)}"
    )
    declared = set(members)
    providers = set(PROVIDER_NAMES)
    missing = providers - declared
    stale = declared - providers
    assert not missing, f"providers with no webhook profile: {sorted(missing)}"
    assert not stale, f"WEBHOOK_PROFILES names that are not real providers: {sorted(stale)}"


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_webhook_profile_matches_implementation(name):
    declared = _declared_webhook_profile(name)
    detected = _detect_webhook_profile(name)
    assert declared == detected, (
        f"{name}: declared webhook profile {declared!r} does not match the implementation "
        f"({detected!r}). Update WEBHOOK_PROFILES, or restore the provider's webhook shape."
    )


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_provider_facade_declares_explicit_all(name):
    package = importlib.import_module(f"bot.payment_providers.{name}")
    assert getattr(package, "__all__", None), (
        f"{name}: package __init__ must declare an explicit __all__ public surface"
    )


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_provider_facade_has_no_leaked_exports(name):
    package = importlib.import_module(f"bot.payment_providers.{name}")
    leaked = sorted(set(package.__all__) & BANNED_FACADE_EXPORTS)
    assert not leaked, (
        f"{name}: provider facade re-exports stdlib/framework/type symbols {leaked}. "
        f"A package __init__ is a public facade, not an implementation barrel — import "
        f"these from their real module instead of re-exporting them."
    )


@pytest.mark.parametrize("name", PROVIDER_NAMES)
def test_provider_facade_exports_resolve(name):
    package = importlib.import_module(f"bot.payment_providers.{name}")
    missing = [n for n in package.__all__ if not hasattr(package, n)]
    assert not missing, f"{name}: __all__ names not importable from the facade: {missing}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
