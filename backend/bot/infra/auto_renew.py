"""Provider-neutral auto-renew primitives shared by the bot and the Web App."""

from __future__ import annotations

from typing import Any


def auto_renew_user_lock_name(user_id: int) -> str:
    """Return the shared lock protecting one customer's renewal consent and charge."""

    return f"auto-renew-user:{int(user_id)}"


def auto_renew_toggle_allowed(provider: Any, *, enable: bool) -> bool:
    """Whether the customer may flip auto-renew for a subscription's provider.

    Saved-method providers support both directions. A provider-managed mandate
    (Platega SBP subscription) is only ever *stopped* from our side: the payer
    authorizes a new mandate at checkout, so re-enabling here would flip a local
    flag that no longer has an upstream schedule behind it.
    """
    from bot.payment_providers import provider_manages_recurring, provider_supports_recurring

    provider_key = str(provider or "").strip().lower()
    if provider_supports_recurring(provider_key):
        return True
    return bool(provider_manages_recurring(provider_key) and not enable)


def recurring_service_for(subscription_service: Any, provider: Any) -> Any:
    """The service that charges a saved method for this provider, if one is wired."""
    provider_key = str(provider or "").strip().lower()
    if not provider_key:
        return None
    resolver = getattr(subscription_service, "recurring_service_for", None)
    if callable(resolver):
        return resolver(provider_key)
    services = getattr(subscription_service, "recurring_provider_services", {}) or {}
    return services.get(provider_key)


async def auto_renew_chargeable(
    session: Any,
    subscription_service: Any,
    *,
    user_id: int,
    provider: Any,
) -> bool:
    """Whether turning auto-renew *on* could actually charge this customer.

    Only saved-method providers can be enabled from our side, and only when their
    recurring service is live and the customer has something it can charge: a
    saved card for card providers or a usable balance for balance renewal. For
    partner balance, check that the profile is active and has funds in the
    renewal currency. A previous payment from it alone does not establish that.
    """
    from bot.payment_providers import provider_supports_recurring
    from bot.payment_providers.shared import service_supports_recurring
    from bot.payment_providers.shared.recurring import has_recurring_payment_method

    provider_key = str(provider or "").strip().lower()
    if not provider_supports_recurring(provider_key):
        return False
    service = recurring_service_for(subscription_service, provider_key)
    if not service_supports_recurring(service):
        return False
    if provider_key == "partner_balance":
        from config.tariffs_config import default_payment_currency_code_for_settings
        from db.dal import partner_dal

        profile = await partner_dal.get_profile_by_user_id(session, int(user_id))
        if profile is None or profile.status != "active":
            return False
        currency = default_payment_currency_code_for_settings(service.settings)
        return await partner_dal.balance_minor(session, int(profile.partner_id), currency) > 0
    return await has_recurring_payment_method(session, int(user_id), provider=provider_key)


def managed_recurring_service_for(subscription_service: Any, provider: Any) -> Any:
    provider_key = str(provider or "").strip().lower()
    if not provider_key:
        return None
    resolver = getattr(subscription_service, "managed_recurring_service_for", None)
    if callable(resolver):
        return resolver(provider_key)
    services = getattr(subscription_service, "managed_recurring_provider_services", {}) or {}
    return services.get(provider_key)


async def stop_provider_managed_recurrence(
    subscription_service: Any,
    session: Any,
    *,
    user_id: int,
    provider: Any,
) -> bool:
    """Cancel the upstream mandate, if the provider owns one for this customer.

    Returns ``False`` when the provider still bills the customer, so callers can
    refuse to report a stopped subscription that is in fact still live.
    """
    from bot.payment_providers.shared import service_manages_recurrence

    service = managed_recurring_service_for(subscription_service, provider)
    if not service_manages_recurrence(service):
        return True
    return bool(await service.cancel_provider_recurrence(session, user_id=int(user_id)))
