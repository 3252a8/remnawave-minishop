from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypeAlias, TypeVar, cast

from aiogram import Bot, Dispatcher
from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.payment_providers import iter_service_keys
from bot.services.email_auth_service import EmailAuthService
from bot.services.notification_service import NotificationService
from bot.services.panel_api_service import PanelApiService
from bot.services.panel_dry_run_api_service import PanelDryRunApiService
from bot.services.panel_webhook_service import PanelWebhookService
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.services.support_service import SupportService
from config.settings import Settings

PanelService: TypeAlias = PanelApiService | PanelDryRunApiService
T = TypeVar("T")


class AppStorage(Protocol):
    def __contains__(self, key: object) -> bool: ...

    def __getitem__(self, key: object) -> object: ...

    def get(self, key: object, default: object = None) -> object: ...


BOT: web.AppKey[Bot] = web.AppKey("bot", Bot)
DISPATCHER: web.AppKey[Dispatcher] = web.AppKey("dp", Dispatcher)
SETTINGS: web.AppKey[Settings] = web.AppKey("settings", Settings)
SESSION_FACTORY: web.AppKey[sessionmaker] = web.AppKey("async_session_factory", sessionmaker)
I18N: web.AppKey[JsonI18n | None] = web.AppKey("i18n", object)
BOT_USERNAME: web.AppKey[str] = web.AppKey("bot_username", str)

PANEL_SERVICE: web.AppKey[PanelService] = web.AppKey("panel_service", object)
SUBSCRIPTION_SERVICE: web.AppKey[SubscriptionService] = web.AppKey(
    "subscription_service", SubscriptionService
)
REFERRAL_SERVICE: web.AppKey[ReferralService] = web.AppKey("referral_service", ReferralService)
PROMO_CODE_SERVICE: web.AppKey[PromoCodeService] = web.AppKey(
    "promo_code_service", PromoCodeService
)
NOTIFICATION_SERVICE: web.AppKey[NotificationService] = web.AppKey(
    "notification_service", NotificationService
)
EMAIL_AUTH_SERVICE: web.AppKey[EmailAuthService] = web.AppKey(
    "email_auth_service", EmailAuthService
)
SUPPORT_SERVICE: web.AppKey[SupportService] = web.AppKey("support_service", SupportService)
PANEL_WEBHOOK_SERVICE: web.AppKey[PanelWebhookService] = web.AppKey(
    "panel_webhook_service", PanelWebhookService
)
LKNPD_SERVICE: web.AppKey[object] = web.AppKey("lknpd_service", object)

PAYMENT_SERVICE_KEYS: dict[str, web.AppKey[object]] = {
    key: web.AppKey(key, object) for key in iter_service_keys()
}


def workflow_data_for(dp: Dispatcher) -> Mapping[str, object]:
    workflow_data = getattr(dp, "workflow_data", {})
    if isinstance(workflow_data, Mapping):
        return workflow_data
    return {}


def _required_value(app: object, app_key: web.AppKey[T], string_key: str) -> T:
    storage = cast(AppStorage, app)
    if app_key in storage:
        return cast(T, storage[app_key])
    return cast(T, storage[string_key])


def _optional_value(app: object, app_key: web.AppKey[T], string_key: str) -> T | None:
    storage = cast(AppStorage, app)
    if app_key in storage:
        return cast(T, storage[app_key])
    return cast(T | None, storage.get(string_key))


def get_settings(request: web.Request) -> Settings:
    return _required_value(request.app, SETTINGS, "settings")


def get_app_settings(app: Mapping[object, object]) -> Settings:
    return _required_value(app, SETTINGS, "settings")


def get_session_factory(request: web.Request) -> sessionmaker:
    return _required_value(request.app, SESSION_FACTORY, "async_session_factory")


def get_bot(request: web.Request) -> Bot:
    return _required_value(request.app, BOT, "bot")


def get_i18n(request: web.Request) -> JsonI18n | None:
    return _optional_value(request.app, I18N, "i18n")


def get_bot_username(request: web.Request) -> str:
    return _optional_value(request.app, BOT_USERNAME, "bot_username") or ""


def get_subscription_service(request: web.Request) -> SubscriptionService:
    return _required_value(request.app, SUBSCRIPTION_SERVICE, "subscription_service")


def get_optional_subscription_service(request: web.Request) -> SubscriptionService | None:
    return _optional_value(request.app, SUBSCRIPTION_SERVICE, "subscription_service")


def get_app_optional_subscription_service(
    app: Mapping[object, object],
) -> SubscriptionService | None:
    return _optional_value(app, SUBSCRIPTION_SERVICE, "subscription_service")


def get_panel_service(request: web.Request) -> PanelService | None:
    return _optional_value(request.app, PANEL_SERVICE, "panel_service")


def get_app_panel_service(app: Mapping[object, object]) -> PanelService | None:
    return _optional_value(app, PANEL_SERVICE, "panel_service")


def get_required_panel_service(request: web.Request) -> PanelService:
    return _required_value(request.app, PANEL_SERVICE, "panel_service")


def get_referral_service(request: web.Request) -> ReferralService | None:
    return _optional_value(request.app, REFERRAL_SERVICE, "referral_service")


def get_required_referral_service(request: web.Request) -> ReferralService:
    return _required_value(request.app, REFERRAL_SERVICE, "referral_service")


def get_promo_code_service(request: web.Request) -> PromoCodeService | None:
    return _optional_value(request.app, PROMO_CODE_SERVICE, "promo_code_service")


def get_support_service(request: web.Request) -> SupportService:
    return _required_value(request.app, SUPPORT_SERVICE, "support_service")


def get_email_auth_service(request: web.Request) -> EmailAuthService:
    return _required_value(request.app, EMAIL_AUTH_SERVICE, "email_auth_service")


def get_payment_service(request: web.Request, key: str) -> object | None:
    app_key = PAYMENT_SERVICE_KEYS.get(key)
    if app_key is not None:
        return _optional_value(request.app, app_key, key)
    return request.app.get(key)


def get_lknpd_service(request: web.Request) -> object | None:
    return _optional_value(request.app, LKNPD_SERVICE, "lknpd_service")


def set_core_context(
    app: web.Application,
    *,
    bot: Bot,
    dp: Dispatcher,
    settings: Settings,
    async_session_factory: sessionmaker,
) -> None:
    i18n = dp.get("i18n_instance")
    app["bot"] = bot
    app[BOT] = bot
    app["dp"] = dp
    app[DISPATCHER] = dp
    app["settings"] = settings
    app[SETTINGS] = settings
    app["async_session_factory"] = async_session_factory
    app[SESSION_FACTORY] = async_session_factory
    app["i18n"] = i18n
    app[I18N] = cast(JsonI18n | None, i18n)


def set_service_context(app: web.Application, key: str, value: object) -> None:
    app[key] = value
    if key == "panel_service":
        app[PANEL_SERVICE] = cast(PanelService, value)
    elif key == "subscription_service":
        app[SUBSCRIPTION_SERVICE] = cast(SubscriptionService, value)
    elif key == "referral_service":
        app[REFERRAL_SERVICE] = cast(ReferralService, value)
    elif key == "promo_code_service":
        app[PROMO_CODE_SERVICE] = cast(PromoCodeService, value)
    elif key == "notification_service":
        app[NOTIFICATION_SERVICE] = cast(NotificationService, value)
    elif key == "email_auth_service":
        app[EMAIL_AUTH_SERVICE] = cast(EmailAuthService, value)
    elif key == "support_service":
        app[SUPPORT_SERVICE] = cast(SupportService, value)
    elif key == "panel_webhook_service":
        app[PANEL_WEBHOOK_SERVICE] = cast(PanelWebhookService, value)
    elif key == "lknpd_service":
        app[LKNPD_SERVICE] = value
    elif key in PAYMENT_SERVICE_KEYS:
        app[PAYMENT_SERVICE_KEYS[key]] = value


def set_bot_username(app: web.Application, value: object) -> None:
    username = str(value)
    app["bot_username"] = username
    app[BOT_USERNAME] = username
