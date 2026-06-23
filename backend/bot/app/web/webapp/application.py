from bot.app.web.context import (
    EMAIL_AUTH_SERVICE,
    set_bot_username,
    set_core_context,
    set_service_context,
    workflow_data_for,
)

from ._runtime import (
    Bot,
    Dispatcher,
    EmailAuthService,
    Settings,
    admin_auth_middleware,
    asyncio,
    sessionmaker,
    web,
)
from .assets import (
    _close_shared_http_session,
    _csrf_protection_middleware,
    _ensure_shared_http_session,
    _security_headers_middleware,
    _warm_webapp_logo_cache,
)
from .guides import warm_subscription_guides_config
from .routes import (
    setup_subscription_webapp_routes,
)


def create_subscription_webapp_application(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
) -> web.Application:
    app = web.Application(
        middlewares=[
            _security_headers_middleware,
            _csrf_protection_middleware,
            admin_auth_middleware,
        ]
    )
    set_core_context(
        app,
        bot=bot,
        dp=dp,
        settings=settings,
        async_session_factory=async_session_factory,
    )
    app["email_auth_service"] = EmailAuthService(settings, app["i18n"])
    app[EMAIL_AUTH_SERVICE] = app["email_auth_service"]
    app["webapp_logo_cache"] = None
    app["webapp_logo_cache_lock"] = asyncio.Lock()
    app["webapp_settings_cache"] = {"ts": 0.0, "data": {}}
    app["subscription_guides_config_cache"] = {"fingerprint": None, "status": None}
    app["subscription_guides_config_lock"] = asyncio.Lock()
    app["subscription_guides_panel_config_cache"] = {}
    app["subscription_guides_panel_config_lock"] = asyncio.Lock()
    app["subscription_guides_resolved_config_cache"] = {}
    app["subscription_guides_resolved_config_lock"] = asyncio.Lock()
    app["subscription_guides_public_subscription_cache"] = {}
    app["subscription_guides_public_subscription_lock"] = asyncio.Lock()
    app["webapp_rate_limit_buckets"] = {}
    app["webapp_rate_limit_lock"] = asyncio.Lock()

    async def _startup(app_obj: web.Application) -> None:
        await _ensure_shared_http_session()
        await _warm_webapp_logo_cache(app_obj)
        await warm_subscription_guides_config(app_obj)

    async def _shutdown(app_obj: web.Application) -> None:
        await _close_shared_http_session()

    app.on_startup.append(_startup)
    app.on_shutdown.append(_shutdown)

    from bot.payment_providers import iter_service_keys

    workflow_data = workflow_data_for(dp)
    for key in (
        "subscription_service",
        "promo_code_service",
        "referral_service",
        "support_service",
        "notification_service",
        "email_auth_service",
        "panel_service",
        *iter_service_keys(),
    ):
        if key in workflow_data:
            set_service_context(app, key, workflow_data[key])

    if "bot_username" in workflow_data:
        set_bot_username(app, workflow_data["bot_username"])

    setup_subscription_webapp_routes(app)
    return app
