from __future__ import annotations

import asyncio
import warnings
from collections import deque
from collections.abc import Callable, Mapping
from typing import Any, Protocol, TypeVar, cast

from aiogram import Bot, Dispatcher
from aiohttp import web
from aiohttp.web_exceptions import NotAppKeyWarning
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
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.services.support_service import SupportService
from config.settings import Settings

type PanelService = PanelApiService | PanelDryRunApiService
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

WEBAPP_SETTINGS_CACHE: web.AppKey[dict[str, Any]] = web.AppKey("webapp_settings_cache", dict)
WEBAPP_RATE_LIMIT_BUCKETS: web.AppKey[dict[str, deque[float]]] = web.AppKey(
    "webapp_rate_limit_buckets", dict
)
WEBAPP_RATE_LIMIT_LOCK: web.AppKey[asyncio.Lock] = web.AppKey(
    "webapp_rate_limit_lock", asyncio.Lock
)
WEBAPP_LOGO_CACHE: web.AppKey[tuple[str, bytes, str] | None] = web.AppKey(
    "webapp_logo_cache", tuple
)
WEBAPP_LOGO_CACHE_LOCK: web.AppKey[asyncio.Lock] = web.AppKey(
    "webapp_logo_cache_lock", asyncio.Lock
)
SUBSCRIPTION_GUIDES_CONFIG_CACHE: web.AppKey[dict[str, Any]] = web.AppKey(
    "subscription_guides_config_cache", dict
)
SUBSCRIPTION_GUIDES_CONFIG_LOCK: web.AppKey[asyncio.Lock] = web.AppKey(
    "subscription_guides_config_lock", asyncio.Lock
)
SUBSCRIPTION_GUIDES_PANEL_CONFIG_CACHE: web.AppKey[dict[Any, Any]] = web.AppKey(
    "subscription_guides_panel_config_cache", dict
)
SUBSCRIPTION_GUIDES_PANEL_CONFIG_LOCK: web.AppKey[asyncio.Lock] = web.AppKey(
    "subscription_guides_panel_config_lock", asyncio.Lock
)
SUBSCRIPTION_GUIDES_RESOLVED_CONFIG_CACHE: web.AppKey[dict[Any, Any]] = web.AppKey(
    "subscription_guides_resolved_config_cache", dict
)
SUBSCRIPTION_GUIDES_RESOLVED_CONFIG_LOCK: web.AppKey[asyncio.Lock] = web.AppKey(
    "subscription_guides_resolved_config_lock", asyncio.Lock
)
SUBSCRIPTION_GUIDES_PUBLIC_SUBSCRIPTION_CACHE: web.AppKey[dict[Any, Any]] = web.AppKey(
    "subscription_guides_public_subscription_cache", dict
)
SUBSCRIPTION_GUIDES_PUBLIC_SUBSCRIPTION_LOCK: web.AppKey[asyncio.Lock] = web.AppKey(
    "subscription_guides_public_subscription_lock", asyncio.Lock
)

PAYMENT_SERVICE_KEYS: dict[str, web.AppKey[object]] = {
    key: web.AppKey(key, object) for key in iter_service_keys()
}


def _required_value[T](app: object, app_key: web.AppKey[T], string_key: str) -> T:
    storage = cast(AppStorage, app)
    if app_key in storage:
        return cast(T, storage[app_key])
    return cast(T, storage[string_key])


def _optional_value[T](app: object, app_key: web.AppKey[T], string_key: str) -> T | None:
    storage = cast(AppStorage, app)
    if app_key in storage:
        return cast(T, storage[app_key])
    return cast(T | None, storage.get(string_key))


def _set_compat_string_value(app: web.Application, string_key: str, value: object) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NotAppKeyWarning)
        app[string_key] = cast(Any, value)


def _set_both_values[T](
    app: web.Application,
    key: web.AppKey[T],
    string_key: str,
    value: T,
) -> None:
    app[key] = value
    _set_compat_string_value(app, string_key, value)


def _get_or_set_default[T](
    app: web.Application,
    key: web.AppKey[T],
    string_key: str,
    default_factory: Callable[[], T],
) -> T:
    storage = cast(AppStorage, app)
    if key in storage:
        return cast(T, storage[key])
    if string_key in storage:
        value = cast(T, storage[string_key])
        _set_both_values(app, key, string_key, value)
        return value
    value = default_factory()
    _set_both_values(app, key, string_key, value)
    return value


def get_settings(request: web.Request) -> Settings:
    return _required_value(request.app, SETTINGS, "settings")


def get_app_settings(app: object) -> Settings:
    return _required_value(app, SETTINGS, "settings")


def get_app_session_factory(app: object) -> sessionmaker:
    return _required_value(app, SESSION_FACTORY, "async_session_factory")


def get_app_bot(app: object) -> Bot:
    return _required_value(app, BOT, "bot")


def get_app_i18n(app: object) -> JsonI18n | None:
    return _optional_value(app, I18N, "i18n")


def get_app_subscription_service(app: object) -> SubscriptionService:
    return _required_value(app, SUBSCRIPTION_SERVICE, "subscription_service")


def get_app_required_subscription_service(app: object) -> SubscriptionService:
    return _required_value(app, SUBSCRIPTION_SERVICE, "subscription_service")


def get_session_factory(request: web.Request) -> sessionmaker:
    return get_app_session_factory(request.app)


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


def get_webapp_settings_cache(request: web.Request) -> dict[str, Any]:
    return _required_value(request.app, WEBAPP_SETTINGS_CACHE, "webapp_settings_cache")


def get_app_webapp_settings_cache(app: object) -> dict[str, Any]:
    return _required_value(app, WEBAPP_SETTINGS_CACHE, "webapp_settings_cache")


def get_webapp_rate_limit_buckets(request: web.Request) -> dict[str, deque[float]]:
    return _required_value(request.app, WEBAPP_RATE_LIMIT_BUCKETS, "webapp_rate_limit_buckets")


def get_webapp_rate_limit_lock(request: web.Request) -> asyncio.Lock:
    return _required_value(request.app, WEBAPP_RATE_LIMIT_LOCK, "webapp_rate_limit_lock")


def get_webapp_logo_cache(
    app: Mapping[object, object],
) -> tuple[str, bytes, str] | None:
    return _optional_value(app, WEBAPP_LOGO_CACHE, "webapp_logo_cache")


def get_webapp_logo_cache_lock(app: Mapping[object, object]) -> asyncio.Lock:
    return _required_value(app, WEBAPP_LOGO_CACHE_LOCK, "webapp_logo_cache_lock")


def set_webapp_logo_cache(app: web.Application, cache: tuple[str, bytes, str] | None) -> None:
    _set_both_values(
        app,
        WEBAPP_LOGO_CACHE,
        "webapp_logo_cache",
        cast(tuple[str, bytes, str] | None, cache),
    )


def get_subscription_guides_config_cache(app: web.Application) -> dict[str, Any]:
    return _required_value(
        app,
        SUBSCRIPTION_GUIDES_CONFIG_CACHE,
        "subscription_guides_config_cache",
    )


def get_subscription_guides_config_lock(app: web.Application) -> asyncio.Lock:
    return _required_value(app, SUBSCRIPTION_GUIDES_CONFIG_LOCK, "subscription_guides_config_lock")


def get_or_create_subscription_guides_config_cache(app: web.Application) -> dict[str, Any]:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_CONFIG_CACHE,
        "subscription_guides_config_cache",
        lambda: {"fingerprint": None, "status": None},
    )


def get_or_create_subscription_guides_config_lock(app: web.Application) -> asyncio.Lock:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_CONFIG_LOCK,
        "subscription_guides_config_lock",
        asyncio.Lock,
    )


def get_or_create_subscription_guides_panel_config_cache(app: web.Application) -> dict[Any, Any]:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_PANEL_CONFIG_CACHE,
        "subscription_guides_panel_config_cache",
        lambda: {},
    )


def get_or_create_subscription_guides_panel_config_lock(app: web.Application) -> asyncio.Lock:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_PANEL_CONFIG_LOCK,
        "subscription_guides_panel_config_lock",
        asyncio.Lock,
    )


def get_or_create_subscription_guides_resolved_config_cache(app: web.Application) -> dict[Any, Any]:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_RESOLVED_CONFIG_CACHE,
        "subscription_guides_resolved_config_cache",
        lambda: {},
    )


def get_or_create_subscription_guides_resolved_config_lock(app: web.Application) -> asyncio.Lock:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_RESOLVED_CONFIG_LOCK,
        "subscription_guides_resolved_config_lock",
        asyncio.Lock,
    )


def get_or_create_subscription_guides_public_subscription_cache(
    app: web.Application,
) -> dict[Any, Any]:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_PUBLIC_SUBSCRIPTION_CACHE,
        "subscription_guides_public_subscription_cache",
        lambda: {},
    )


def get_or_create_subscription_guides_public_subscription_lock(
    app: web.Application,
) -> asyncio.Lock:
    return _get_or_set_default(
        app,
        SUBSCRIPTION_GUIDES_PUBLIC_SUBSCRIPTION_LOCK,
        "subscription_guides_public_subscription_lock",
        asyncio.Lock,
    )


def get_panel_service(request: web.Request) -> PanelService | None:
    return _optional_value(request.app, PANEL_SERVICE, "panel_service")


def get_app_panel_service(app: object) -> PanelService | None:
    return _optional_value(app, PANEL_SERVICE, "panel_service")


def get_app_referral_service(app: object) -> ReferralService:
    return _required_value(app, REFERRAL_SERVICE, "referral_service")


def get_required_panel_service(request: web.Request) -> PanelService:
    return _required_value(request.app, PANEL_SERVICE, "panel_service")


def get_referral_service(request: web.Request) -> ReferralService | None:
    return _optional_value(request.app, REFERRAL_SERVICE, "referral_service")


def get_app_required_referral_service(app: object) -> ReferralService:
    return _required_value(app, REFERRAL_SERVICE, "referral_service")


def get_required_referral_service(request: web.Request) -> ReferralService:
    return _required_value(request.app, REFERRAL_SERVICE, "referral_service")


def get_panel_webhook_service(request: web.Request) -> PanelWebhookService:
    return _required_value(request.app, PANEL_WEBHOOK_SERVICE, "panel_webhook_service")


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
    _set_both_values(app, BOT, "bot", bot)
    _set_both_values(app, DISPATCHER, "dp", dp)
    _set_both_values(app, SETTINGS, "settings", settings)
    _set_both_values(app, SESSION_FACTORY, "async_session_factory", async_session_factory)
    _set_both_values(app, I18N, "i18n", cast(JsonI18n | None, i18n))


def initialize_webapp_runtime_context(app: web.Application) -> None:
    _set_both_values(
        app,
        WEBAPP_SETTINGS_CACHE,
        "webapp_settings_cache",
        {"ts": 0.0, "data": {}},
    )
    _set_both_values(app, WEBAPP_RATE_LIMIT_BUCKETS, "webapp_rate_limit_buckets", {})
    _set_both_values(app, WEBAPP_RATE_LIMIT_LOCK, "webapp_rate_limit_lock", asyncio.Lock())
    _set_both_values(app, WEBAPP_LOGO_CACHE, "webapp_logo_cache", None)
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_CONFIG_CACHE,
        "subscription_guides_config_cache",
        {"fingerprint": None, "status": None},
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_CONFIG_LOCK,
        "subscription_guides_config_lock",
        asyncio.Lock(),
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_PANEL_CONFIG_CACHE,
        "subscription_guides_panel_config_cache",
        {},
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_PANEL_CONFIG_LOCK,
        "subscription_guides_panel_config_lock",
        asyncio.Lock(),
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_RESOLVED_CONFIG_CACHE,
        "subscription_guides_resolved_config_cache",
        {},
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_RESOLVED_CONFIG_LOCK,
        "subscription_guides_resolved_config_lock",
        asyncio.Lock(),
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_PUBLIC_SUBSCRIPTION_CACHE,
        "subscription_guides_public_subscription_cache",
        {},
    )
    _set_both_values(
        app,
        SUBSCRIPTION_GUIDES_PUBLIC_SUBSCRIPTION_LOCK,
        "subscription_guides_public_subscription_lock",
        asyncio.Lock(),
    )


def set_service_context(app: web.Application, key: str, value: object) -> None:
    _set_compat_string_value(app, key, value)
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
    _set_both_values(app, BOT_USERNAME, "bot_username", username)
