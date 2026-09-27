"""Internal checkout method for purchases funded entirely from an account balance."""

from aiohttp import web

from bot.payment_providers.base import PaymentProviderSpec, WebAppPaymentContext

from .common import _json_error


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
