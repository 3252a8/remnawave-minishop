"""Feature entitlement registry used by core and extension plugins.

The open core exposes a small feature-query contract so optional extensions
can advertise capabilities without changing core code paths. By default no
feature is gated or advertised.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol

logger = logging.getLogger(__name__)

MARKETING_WINBACK_ENTITLEMENT = "marketing.winback"
MARKETING_CAMPAIGNS_ENTITLEMENT = "marketing.campaigns"
RESERVED_ENTITLEMENT_KEYS = frozenset(
    {
        MARKETING_WINBACK_ENTITLEMENT,
        MARKETING_CAMPAIGNS_ENTITLEMENT,
    }
)


class EntitlementsProviderConflictError(RuntimeError):
    """Raised when more than one plugin claims entitlement authority."""


class EntitlementsProvider(Protocol):
    """Provider that answers whether a named feature is available."""

    def has_feature(self, name: str) -> bool:
        """Return True when ``name`` is available."""

    def features(self) -> set[str]:
        """Return all available feature names."""


class DefaultEntitlements:
    """Static entitlement set used when no plugin supplies a provider."""

    def __init__(self, features: Iterable[str] | None = None) -> None:
        self._features = frozenset(
            normalized for name in features or () if (normalized := _normalize_feature(name))
        )

    def has_feature(self, name: str) -> bool:
        return _normalize_feature(name) in self._features

    def features(self) -> set[str]:
        return set(self._features)


def _normalize_feature(name: str) -> str:
    return str(name or "").strip()


_provider: EntitlementsProvider = DefaultEntitlements()
_provider_source = "core"


def get_entitlements() -> EntitlementsProvider:
    """Return the active entitlements provider."""
    return _provider


def active_entitlements_source() -> str:
    """Return the plugin/core identifier that supplied the active provider."""
    return _provider_source


def set_entitlements_provider(
    provider: EntitlementsProvider,
    *,
    source: str = "core",
) -> None:
    """Set the active provider and log the owning source."""
    global _provider, _provider_source
    _provider = provider
    _provider_source = str(source or "core")
    logger.info("Entitlements provider active: %s", _provider_source)


def reset_entitlements() -> None:
    """Restore the default provider (primarily for tests)."""
    global _provider, _provider_source
    _provider = DefaultEntitlements()
    _provider_source = "core"


def has_feature(name: str) -> bool:
    """Safely check a feature against the active provider."""
    try:
        return bool(_provider.has_feature(name))
    except Exception:
        logger.exception("Entitlements provider %s failed in has_feature", _provider_source)
        return False


def features() -> set[str]:
    """Safely return the active feature set."""
    try:
        return {
            normalized for name in _provider.features() if (normalized := _normalize_feature(name))
        }
    except Exception:
        logger.exception("Entitlements provider %s failed in features", _provider_source)
        return set()
