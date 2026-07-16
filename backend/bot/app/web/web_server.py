import asyncio
import functools
import hmac
import logging
from collections.abc import Awaitable, Callable
from typing import Any, cast

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiohttp.web_log import AccessLogger, KeyMethod
from sqlalchemy.orm import sessionmaker

from bot.app.controllers.dispatcher_context import iter_dispatcher_services
from bot.app.web.context import (
    get_app_settings,
    set_core_context,
    set_service_context,
)
from bot.infra.observability import (
    ERROR_REPORTER_SERVICE_KEY,
    METRICS_SERVICE_KEY,
    observability_error_middleware,
)
from bot.payment_providers import iter_provider_specs, iter_service_keys
from bot.plugins import (
    WEB_SCOPE_WEBAPP,
    WEB_SCOPE_WEBHOOKS,
    PluginContext,
    setup_web_plugins,
)
from bot.utils.request_security import request_client_ip
from config.settings import Settings

logger = logging.getLogger(__name__)


class SecureSimpleRequestHandler(SimpleRequestHandler):
    def verify_secret(self, telegram_secret_token: str, bot: Bot) -> bool:
        if not self.secret_token:
            return False
        return hmac.compare_digest(telegram_secret_token, self.secret_token)


class TrustedProxyAccessLogger(AccessLogger):
    """Aiohttp access logger that respects trusted X-Forwarded-For headers."""

    def compile_format(self, log_format: str) -> tuple[str, list[KeyMethod]]:
        methods = []
        for atom in self.FORMAT_RE.findall(log_format):
            if atom[1] == "":
                format_key: str | tuple[str, str] = self.LOG_FORMAT_MAP[atom[0]]
                method = getattr(type(self), f"_format_{atom[0]}", None)
                if method is None:
                    method = getattr(AccessLogger, f"_format_{atom[0]}")
                methods.append(KeyMethod(format_key, method))
            else:
                format_key = (self.LOG_FORMAT_MAP[atom[2]], atom[1])
                method = getattr(type(self), f"_format_{atom[2]}", None)
                if method is None:
                    method = getattr(AccessLogger, f"_format_{atom[2]}")
                methods.append(KeyMethod(format_key, functools.partial(method, atom[1])))

        compiled = self.FORMAT_RE.sub(r"%s", log_format)
        compiled = self.CLEANUP_RE.sub(r"%\1", compiled)
        return compiled, methods

    @staticmethod
    def _format_a(request: web.BaseRequest, response: web.StreamResponse, time: float) -> str:
        if request is None:
            return "-"
        app = getattr(request, "app", None)
        settings = get_app_settings(app) if app is not None else None
        trusted_proxies = settings.trusted_proxies if settings is not None else None
        client_ip = request_client_ip(cast(web.Request, request), trusted_proxies=trusted_proxies)
        return client_ip or "-"


def _inject_shared_instances(
    app: web.Application,
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
) -> None:
    set_core_context(
        app,
        bot=bot,
        dp=dp,
        settings=settings,
        async_session_factory=async_session_factory,
    )
    shared_keys = [
        "subscription_service",
        "referral_service",
        "panel_service",
        "panel_webhook_service",
        "lknpd_service",
        *iter_service_keys(),
    ]
    for key, service in iter_dispatcher_services(dp, shared_keys):
        set_service_context(app, key, service)


def _inject_observability_instances(app: web.Application, ctx: PluginContext) -> None:
    set_service_context(app, ERROR_REPORTER_SERVICE_KEY, ctx.error_reporter)
    set_service_context(app, METRICS_SERVICE_KEY, ctx.metrics)


async def build_and_start_web_app(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
    *,
    after_webhooks_started: Callable[[], Awaitable[None]] | None = None,
    plugin_context: PluginContext | None = None,
) -> None:
    app = web.Application(middlewares=[observability_error_middleware])
    _inject_shared_instances(app, dp, bot, settings, async_session_factory)
    if plugin_context is not None:
        _inject_observability_instances(app, plugin_context)

    async def _healthcheck(request: web.Request) -> web.Response:
        payload: dict[str, Any] = {"status": "ok"}
        try:
            from db.database_setup import async_engine

            pool = async_engine.pool if async_engine is not None else None
            if pool is not None:
                payload["db_pool"] = {
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "size": pool.size(),
                    "overflow": pool.overflow(),
                }
        except Exception:
            logger.exception("Failed to collect DB pool health metrics")
        return web.json_response(payload)

    app.router.add_get("/healthz", _healthcheck)
    app.router.add_get("/health", _healthcheck)

    setup_application(app, dp, bot=bot)

    telegram_uses_webhook_mode = bool(settings.WEBHOOK_BASE_URL)

    if telegram_uses_webhook_mode:
        telegram_webhook_path = settings.telegram_webhook_path
        SecureSimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.WEBHOOK_SECRET_TOKEN,
        ).register(app, path=telegram_webhook_path)
        logger.info(
            "Telegram webhook route configured at: [POST] %s (relative to base URL)",
            telegram_webhook_path,
        )

    from bot.services.panel_webhook_service import panel_webhook_route

    registered_webhook_paths: set[str] = set()
    for spec in iter_provider_specs():
        webhook_route = spec.load_webhook_route()
        if not spec.webhook_path or not webhook_route:
            continue
        if spec.webhook_requires_base_url and not settings.WEBHOOK_BASE_URL:
            continue
        path = spec.webhook_path(settings)
        if not path or not path.startswith("/") or path in registered_webhook_paths:
            continue
        registered_webhook_paths.add(path)
        app.router.add_post(path, webhook_route)
        logger.info("%s webhook route configured at: [POST] %s", spec.label, path)

    panel_path = settings.panel_webhook_path
    if panel_path.startswith("/"):
        app.router.add_post(panel_path, panel_webhook_route)
        logger.info("Panel webhook route configured at: [POST] %s", panel_path)

    if plugin_context is not None:
        setup_web_plugins(plugin_context, app, scope=WEB_SCOPE_WEBHOOKS)

    runners = []

    webhooks_runner = web.AppRunner(app, access_log_class=TrustedProxyAccessLogger)
    await webhooks_runner.setup()
    runners.append(webhooks_runner)
    site = web.TCPSite(
        webhooks_runner,
        host=settings.WEB_SERVER_HOST,
        port=settings.web_server_listen_port,
    )

    await site.start()
    logger.info(
        "AIOHTTP server started on http://%s:%s",
        settings.WEB_SERVER_HOST,
        settings.web_server_listen_port,
    )

    # The webapp listener must open before after_webhooks_started: webhook
    # configuration talks to the Telegram API with unbounded retries, and while
    # it runs the container already reports healthy (the /healthz port is up),
    # so a late webapp port shows up as "bot works, webapp is down".
    webapp_settings = settings.webapp_settings
    if webapp_settings.enabled:
        from bot.app.web.webapp.application import create_subscription_webapp_application

        subscription_app = create_subscription_webapp_application(
            dp,
            bot,
            settings,
            async_session_factory,
        )
        if plugin_context is not None:
            _inject_observability_instances(subscription_app, plugin_context)
            setup_web_plugins(plugin_context, subscription_app, scope=WEB_SCOPE_WEBAPP)
        subscription_runner = web.AppRunner(
            subscription_app,
            access_log_class=TrustedProxyAccessLogger,
        )
        await subscription_runner.setup()
        runners.append(subscription_runner)
        subscription_site = web.TCPSite(
            subscription_runner,
            host=webapp_settings.server_host,
            port=webapp_settings.server_port,
        )
        await subscription_site.start()
        logger.info(
            "Subscription WebApp server started on http://%s:%s",
            webapp_settings.server_host,
            webapp_settings.server_port,
        )

    if after_webhooks_started is not None:
        await after_webhooks_started()

    try:
        await asyncio.Event().wait()
    finally:
        for runner in reversed(runners):
            try:
                await runner.cleanup()
            except Exception as cleanup_error:
                logger.warning("Failed to cleanup aiohttp runner: %s", cleanup_error)
