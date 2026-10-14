"""Internal checkout method for purchases funded entirely from an account balance."""

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.payment_providers.base import PaymentProviderSpec, WebAppPaymentContext
from bot.payment_providers.shared.common import sale_mode_base
from bot.services.balance_recurring import (
    BALANCE_RECURRING_ADDON_BASES,
    balance_recurrence_blocks_purchase,
    balance_recurring_available,
)
from bot.services.subscription_gifts import is_gift_sale
from config.settings import Settings
from db.dal import subscription_dal
from db.models import Subscription

from .common import _json_error


async def balance_checkout_policy(
    *,
    session: AsyncSession,
    user_id: int,
    settings: Settings,
    sale_mode: str,
    source: str | None,
    auto_renew: bool,
) -> tuple[web.Response | None, Subscription | None]:
    active_sub = None
    if sale_mode_base(sale_mode) in BALANCE_RECURRING_ADDON_BASES:
        active_sub = await subscription_dal.get_active_subscription_by_user_id(session, user_id)
        if balance_recurrence_blocks_purchase(active_sub, sale_mode):
            return (
                _json_error(
                    409,
                    "balance_recurring_conflict",
                    "Disable balance auto-renew before buying separate add-ons",
                ),
                active_sub,
            )
    provider = "user_balance" if source == "user" else "partner_balance"
    if auto_renew and (
        source is None
        or sale_mode_base(sale_mode) != "subscription"
        or is_gift_sale(sale_mode)
        or not balance_recurring_available(settings, provider)
    ):
        return (
            _json_error(409, "balance_auto_renew_unavailable", "Balance auto-renew is unavailable"),
            active_sub,
        )
    return None, active_sub


async def _reject_external_remainder(context: WebAppPaymentContext) -> web.Response:
    # The normal balance finalizer handles a fully funded quote before this point.
    return _json_error(409, "balance_insufficient", "Balance does not cover the current quote")


BALANCE_CHECKOUT_SPEC = PaymentProviderSpec(
    id="balance",
    provider_key="balance",
    label="Balance",
    pending_status="pending",
    enabled=lambda settings: True,
    requires_configured_service=False,
    supported_currencies=None,
    create_webapp_payment=_reject_external_remainder,
)


def checkout_provider_spec(method: str) -> PaymentProviderSpec | None:
    from bot.payment_providers import get_provider_spec

    return BALANCE_CHECKOUT_SPEC if method == "balance" else get_provider_spec(method)
