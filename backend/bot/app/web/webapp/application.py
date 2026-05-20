# ruff: noqa: F401,F403,F405,I001
from ._runtime import *  # noqa: F403,F405


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
    app["bot"] = bot
    app["dp"] = dp
    app["settings"] = settings
    app["async_session_factory"] = async_session_factory
    app["i18n"] = dp.get("i18n_instance")
    app["email_auth_service"] = EmailAuthService(settings)
    app["webapp_logo_cache"] = None
    app["webapp_logo_cache_lock"] = asyncio.Lock()
    app["webapp_settings_cache"] = {"ts": 0.0, "data": {}}
    app["webapp_rate_limit_buckets"] = {}
    app["webapp_rate_limit_lock"] = asyncio.Lock()

    async def _startup(app_obj: web.Application) -> None:
        await _ensure_shared_http_session()
        await _warm_webapp_logo_cache(app_obj)
        await _warm_webapp_animated_emoji_cache(app_obj)

    async def _shutdown(app_obj: web.Application) -> None:
        await _close_shared_http_session()

    app.on_startup.append(_startup)
    app.on_shutdown.append(_shutdown)

    from bot.payment_providers import iter_service_keys

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
        if hasattr(dp, "workflow_data") and key in dp.workflow_data:  # type: ignore[attr-defined]
            app[key] = dp.workflow_data[key]  # type: ignore[index]

    if hasattr(dp, "workflow_data") and "bot_username" in dp.workflow_data:  # type: ignore[attr-defined]
        app["bot_username"] = dp.workflow_data["bot_username"]  # type: ignore[index]

    setup_subscription_webapp_routes(app)
    return app
