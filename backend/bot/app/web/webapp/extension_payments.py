"""Discover only adapters able to charge the exact currency and frozen order price."""

from aiohttp import web

from bot.app.web.context import get_settings
from bot.payment_providers import iter_provider_specs
from bot.payment_providers.base import PaymentProviderSpec
from bot.plugins.extensions.contracts import ProductQuote
from bot.services.partner_common import currency_scale, minor_to_decimal_string
from config.settings import Settings


def payment_methods(
    settings: Settings, app: web.Application, *, is_admin: bool, quote: ProductQuote, order_id: str
) -> list[PaymentProviderSpec]:
    mode = f"extension|{order_id}"
    amount = minor_to_decimal_string(quote.amount_minor, scale=currency_scale(quote.currency))
    return [
        spec
        for spec in iter_provider_specs()
        if spec.create_webapp_payment is not None
        and not spec.manages_recurring
        and (spec.price_source == "stars") == (quote.currency == "XTR")
        and not spec.is_price_managed_externally(settings, 1, mode)
        and spec.is_visible_for_user(settings, app, is_admin=is_admin)
        and spec.is_usable_for_payment(settings, quote.currency, amount)
        and spec.is_usable_for_payment_context(settings, 1, mode)
    ]


def balance_available(request: web.Request, quote: ProductQuote) -> bool:
    settings = get_settings(request)
    return settings.USER_BALANCE_ENABLED and quote.currency == settings.USER_BALANCE_CURRENCY
