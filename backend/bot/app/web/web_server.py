import asyncio
import hmac
import logging

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy.orm import sessionmaker

from bot.payment_providers import iter_provider_specs, iter_service_keys
from config.settings import Settings


class SecureSimpleRequestHandler(SimpleRequestHandler):
    def verify_secret(self, telegram_secret_token: str, bot: Bot) -> bool:
        if not self.secret_token:
            return False
        return hmac.compare_digest(telegram_secret_token, self.secret_token)


def _inject_shared_instances(
    app: web.Application,
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
) -> None:
    app["bot"] = bot
    app["dp"] = dp
    app["settings"] = settings
    app["async_session_factory"] = async_session_factory
    app["i18n"] = dp.get("i18n_instance")
    shared_keys = [
        "subscription_service",
        "referral_service",
        "panel_service",
        "panel_webhook_service",
        "lknpd_service",
        *iter_service_keys(),
    ]
    for key in shared_keys:
        if hasattr(dp, "workflow_data") and key in dp.workflow_data:  # type: ignore
            app[key] = dp.workflow_data[key]  # type: ignore


async def build_and_start_web_app(
    dp: Dispatcher,
    bot: Bot,
    settings: Settings,
    async_session_factory: sessionmaker,
):
    app = web.Application()
    _inject_shared_instances(app, dp, bot, settings, async_session_factory)

    async def _healthcheck(request: web.Request) -> web.Response:
        payload = {"status": "ok"}
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
            logging.exception("Failed to collect DB pool health metrics")
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
        logging.info(
            f"Telegram webhook route configured at: [POST] {telegram_webhook_path} (relative to base URL)"  # noqa: E501
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
        logging.info("%s webhook route configured at: [POST] %s", spec.label, path)

    panel_path = settings.panel_webhook_path
    if panel_path.startswith("/"):
        app.router.add_post(panel_path, panel_webhook_route)
        logging.info(f"Panel webhook route configured at: [POST] {panel_path}")

    runners = []

    webhooks_runner = web.AppRunner(app)
    await webhooks_runner.setup()
    runners.append(webhooks_runner)
    site = web.TCPSite(
        webhooks_runner,
        host=settings.WEB_SERVER_HOST,
        port=settings.WEB_SERVER_PORT,
    )

    await site.start()
    logging.info(
        f"AIOHTTP server started on http://{settings.WEB_SERVER_HOST}:{settings.WEB_SERVER_PORT}"
    )

    if settings.WEBAPP_ENABLED:
        from bot.app.web.subscription_webapp import create_subscription_webapp_application

        subscription_app = create_subscription_webapp_application(
            dp,
            bot,
            settings,
            async_session_factory,
        )
        subscription_runner = web.AppRunner(subscription_app)
        await subscription_runner.setup()
        runners.append(subscription_runner)
        subscription_site = web.TCPSite(
            subscription_runner,
            host=settings.WEBAPP_SERVER_HOST,
            port=settings.WEBAPP_SERVER_PORT,
        )
        await subscription_site.start()
        logging.info(
            "Subscription WebApp server started on http://%s:%s",
            settings.WEBAPP_SERVER_HOST,
            settings.WEBAPP_SERVER_PORT,
        )

    try:
        await asyncio.Event().wait()
    finally:
        for runner in reversed(runners):
            try:
                await runner.cleanup()
            except Exception as cleanup_error:
                logging.warning("Failed to cleanup aiohttp runner: %s", cleanup_error)
