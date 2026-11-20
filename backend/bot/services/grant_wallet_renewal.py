"""Select the first paid wallet period for trial and administrator grants."""

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.partner_common import amount_to_minor, currency_scale
from config.settings import Settings
from config.subscription_periods import legacy_months_to_days
from config.tariffs_config import (
    Tariff,
    TariffsConfig,
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.balance_renewal import GRANT_PROVIDERS, GrantBalanceRenewal, subscription_provider
from db.dal import auto_renew_dal, subscription_dal
from db.models import Subscription


def _first_paid_period(tariff: Tariff, currency: str) -> tuple[int, float] | None:
    if tariff.billing_model == "period":
        for period in sorted(tariff.enabled_periods):
            price = tariff.period_price(period, currency)
            if price is not None and price > 0:
                return tariff.period_duration_days(period), price
    return None


def _default_tariff_key(catalog: TariffsConfig, currency: str) -> str | None:
    keys = [t.key for t in catalog.enabled_tariffs if _first_paid_period(t, currency)]
    if len(keys) == 1:
        return keys[0]
    return catalog.default_tariff if catalog.default_tariff in keys else None


def grant_balance_renewal_tariff_key(
    settings: Settings, subscription: Subscription | None
) -> str | None:
    provider = subscription_provider(subscription)
    if provider not in GRANT_PROVIDERS or not (catalog := settings.tariffs_config):
        return None
    currency = default_currency_key_for_settings(settings)
    if provider == "admin" and subscription is not None and subscription.tariff_key:
        assigned = catalog.get(subscription.tariff_key)
        return assigned.key if assigned and _first_paid_period(assigned, currency) else None
    return _default_tariff_key(catalog, currency)


async def schedule_funded_grants(session: AsyncSession, settings: Settings, limit: int) -> None:
    currency = default_payment_currency_code_for_settings(settings)
    if currency != settings.balance_settings.currency.upper():
        return
    catalog = settings.tariffs_config
    price_currency = default_currency_key_for_settings(settings)
    scale = currency_scale(currency)
    terms: dict[str, GrantBalanceRenewal] = {}
    prices: dict[str, int] = {}
    if catalog is None:
        # An empty key represents the unscoped subscription sold by legacy checkout.
        default_key: str | None = ""
        for months, price in sorted(settings.subscription_options.items()):
            if price > 0:
                terms[""] = GrantBalanceRenewal("user_balance", "", legacy_months_to_days(months))
                prices[""] = amount_to_minor(price, scale=scale)
                break
    else:
        default_key = _default_tariff_key(catalog, price_currency)
        for tariff in catalog.tariffs:
            if first_period := _first_paid_period(tariff, price_currency):
                days, price = first_period
                minor = amount_to_minor(price, scale=scale)
                if minor <= 0:
                    continue
                for key in (tariff.key, *tariff.legacy_keys):
                    terms[key] = GrantBalanceRenewal("user_balance", tariff.key, days)
                    prices[key] = minor
    if not terms:
        return
    grants = await auto_renew_dal.list_funded_grants(
        session,
        currency=currency,
        prices_minor=prices,
        default_tariff_key=default_key,
        limit=limit,
    )
    for subscription, tariff_key in grants:
        await subscription_dal.set_auto_renew(
            session, subscription.subscription_id, True, balance_renewal=terms[tariff_key]
        )
