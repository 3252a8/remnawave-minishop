from aiogram import Bot
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.payment_providers import ServiceFactoryContext, build_provider_services
from bot.services.lknpd_service import LknpdService
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_webhook_service import PanelWebhookService
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from config.settings import Settings


def build_core_services(
    settings: Settings,
    bot: Bot,
    async_session_factory: sessionmaker,
    i18n: JsonI18n,
    bot_username_for_default_return: str,
):
    panel_service = PanelApiService(settings)
    subscription_service = SubscriptionService(settings, panel_service, bot, i18n)
    referral_service = ReferralService(settings, subscription_service, bot, i18n)
    promo_code_service = PromoCodeService(settings, subscription_service, bot, i18n)
    panel_webhook_service = PanelWebhookService(
        bot, settings, i18n, async_session_factory, panel_service
    )
    payment_services = build_provider_services(
        ServiceFactoryContext(
            settings=settings,
            bot=bot,
            async_session_factory=async_session_factory,
            i18n=i18n,
            bot_username_for_default_return=bot_username_for_default_return,
            subscription_service=subscription_service,
            referral_service=referral_service,
        )
    )
    lknpd_service = LknpdService(
        settings.LKNPD_INN,
        settings.LKNPD_PASSWORD,
        api_url=settings.LKNPD_API_URL,
    )

    # These attachments are critical for auto-renew and panel pre-expiry hooks.
    subscription_service.yookassa_service = payment_services.get("yookassa_service")
    panel_webhook_service.subscription_service = subscription_service

    services = {
        "panel_service": panel_service,
        "subscription_service": subscription_service,
        "referral_service": referral_service,
        "promo_code_service": promo_code_service,
        "panel_webhook_service": panel_webhook_service,
        "lknpd_service": lknpd_service,
    }
    services.update(payment_services)
    return services
