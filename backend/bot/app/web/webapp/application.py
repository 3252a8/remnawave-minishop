import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.app.controllers.dispatcher_context import (
    get_dispatcher_bot_username,
    iter_dispatcher_services,
)
from bot.app.web.admin_api_impl.auth import (
    admin_auth_middleware,
)
from bot.app.web.context import (
    EMAIL_AUTH_SERVICE,
    get_app_i18n,
    initialize_webapp_runtime_context,
    set_bot_username,
    set_core_context,
    set_service_context,
)
from bot.infra.observability import observability_error_middleware
from bot.services.email_auth_service import EmailAuthService
from config.settings import Settings

from .assets import (
    _close_shared_http_session,
    _csrf_protection_middleware,
    _ensure_shared_http_session,
    _security_headers_middleware,
    _warm_webapp_logo_cache,
    _webapp_edge_token_middleware,
)
from .guides import warm_subscription_guides_config
from .routes import (
    setup_subscription_webapp_routes,
)

logger = logging.getLogger(__name__)


def create_subscription_webapp_application(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
) -> web.Application:
    app = web.Application(
        middlewares=[
            observability_error_middleware,
            _security_headers_middleware,
            _webapp_edge_token_middleware,
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
    initialize_webapp_runtime_context(app)
    app[EMAIL_AUTH_SERVICE] = EmailAuthService(settings, get_app_i18n(app))
    set_service_context(app, "email_auth_service", app[EMAIL_AUTH_SERVICE])

    async def _warm_caches(app_obj: web.Application) -> None:
        try:
            await _warm_webapp_logo_cache(app_obj)
        except Exception:
            logger.exception("Failed to warm webapp logo cache")
        await warm_subscription_guides_config(app_obj)

    warmup_task: asyncio.Task[None] | None = None

    # The warms fetch the logo from a remote URL and the guides config from the
    # panel; both may hang on network timeouts right after a restart, so they
    # must not delay opening the webapp listener.
    async def _startup(app_obj: web.Application) -> None:
        nonlocal warmup_task
        await _ensure_shared_http_session()
        warmup_task = asyncio.create_task(_warm_caches(app_obj))

    async def _shutdown(app_obj: web.Application) -> None:
        if warmup_task is not None and not warmup_task.done():
            warmup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await warmup_task
        await _close_shared_http_session()

    app.on_startup.append(_startup)
    app.on_shutdown.append(_shutdown)

    from bot.payment_providers import iter_service_keys

    for key, service in iter_dispatcher_services(
        dp,
        (
            "subscription_service",
            "promo_code_service",
            "referral_service",
            "support_service",
            "notification_service",
            "email_auth_service",
            "panel_service",
            *iter_service_keys(),
        ),
    ):
        set_service_context(app, key, service)

    bot_username = get_dispatcher_bot_username(dp)
    if bot_username:
        set_bot_username(app, bot_username)

    setup_subscription_webapp_routes(app)
    return app
