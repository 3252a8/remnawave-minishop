import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonDefault, MenuButtonWebApp, WebAppInfo
from sqlalchemy.orm import sessionmaker

from bot.app.controllers.dispatcher_controller import build_dispatcher
from bot.app.factories.build_services import build_core_services
from bot.app.web.web_server import build_and_start_web_app
from bot.handlers.admin.sync_admin import perform_sync
from bot.infra.redis import close_redis
from bot.middlewares.i18n import JsonI18n
from bot.routers import build_root_router
from bot.services.panel_api_service import PanelApiService
from bot.services.settings_override_service import load_overrides_from_db
from bot.utils.message_queue import init_queue_manager
from config.settings import Settings
from db.database_setup import init_db_connection


def redact_token(value: str, token: Optional[str]) -> str:
    if not value or not token:
        return value
    return value.replace(token, "***")


async def register_all_routers(dp: Dispatcher, settings: Settings):
    dp.include_router(build_root_router(settings))
    logging.info("All application routers registered.")


async def on_startup_configured(dispatcher: Dispatcher):
    bot: Bot = dispatcher["bot_instance"]
    settings: Settings = dispatcher["settings"]
    i18n_instance: JsonI18n = dispatcher["i18n_instance"]

    logging.info("STARTUP: on_startup_configured executing...")

    telegram_webhook_url_to_set = settings.WEBHOOK_BASE_URL
    if telegram_webhook_url_to_set:
        full_telegram_webhook_url = (
            f"{str(telegram_webhook_url_to_set).rstrip('/')}{settings.telegram_webhook_path}"
        )

        logging.info(
            "STARTUP: Attempting to set Telegram webhook to: %s",
            redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
        )

        try:
            current_webhook_info = await bot.get_webhook_info()
            logging.info(
                f"STARTUP: Current Telegram webhook info BEFORE setting: {current_webhook_info.model_dump_json(exclude_none=True, indent=2)}"  # noqa: E501
            )

            set_success = await bot.set_webhook(
                url=full_telegram_webhook_url,
                secret_token=settings.WEBHOOK_SECRET_TOKEN,
                drop_pending_updates=True,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
            if set_success:
                logging.info(
                    "STARTUP: bot.set_webhook to %s returned SUCCESS (True).",
                    redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
                )
            else:
                logging.error(
                    "STARTUP: bot.set_webhook to %s returned FAILURE (False).",
                    redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
                )

            new_webhook_info = await bot.get_webhook_info()
            logging.info(
                f"STARTUP: Telegram Webhook info AFTER setting: {new_webhook_info.model_dump_json(exclude_none=True, indent=2)}"  # noqa: E501
            )
            if not new_webhook_info.url:
                logging.error(
                    "STARTUP: CRITICAL - Telegram Webhook URL is EMPTY after set attempt. Check bot token and URL validity."  # noqa: E501
                )

        except Exception:
            logging.exception("STARTUP: EXCEPTION during set/get Telegram webhook.")
    else:
        logging.error(
            "STARTUP: WEBHOOK_BASE_URL not set in environment. Webhook mode is required. Exiting."
        )
        raise SystemExit("WEBHOOK_BASE_URL is required. Polling mode is disabled.")

    if settings.SUBSCRIPTION_MINI_APP_URL:
        try:
            menu_text = i18n_instance.gettext(
                settings.DEFAULT_LANGUAGE,
                "menu_personal_account_button",
            )
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text=menu_text,
                    web_app=WebAppInfo(url=settings.SUBSCRIPTION_MINI_APP_URL),
                )
            )
            await bot.set_chat_menu_button(menu_button=MenuButtonDefault())
            logging.info("STARTUP: Mini app domain registered and default menu button restored.")
        except Exception:
            logging.exception("STARTUP: Failed to register mini app domain.")

    try:
        bot_commands = [
            BotCommand(command="tg", description="Интерфейс в боте"),
        ]
        if settings.START_COMMAND_DESCRIPTION:
            bot_commands.insert(
                0,
                BotCommand(command="start", description=settings.START_COMMAND_DESCRIPTION),
            )
        await bot.set_my_commands(bot_commands)
        logging.info("STARTUP: bot command descriptions set.")
    except Exception:
        logging.exception("STARTUP: Failed to set bot commands.")

    # Initialize message queue manager
    try:
        queue_manager = init_queue_manager(bot)
        dispatcher["queue_manager"] = queue_manager
        logging.info("STARTUP: Message queue manager initialized")
    except Exception:
        logging.exception("STARTUP: Failed to initialize message queue manager.")

    # Automatic sync on startup — runs in background so the dispatcher can
    # start serving Telegram webhooks immediately even if the panel is slow.
    # perform_sync is single-flight, so concurrent admin-triggered runs will
    # be skipped while this one is in progress.
    logging.info("STARTUP: Bot on_startup_configured completed.")


async def _background_startup_sync(
    *,
    panel_service: PanelApiService,
    session_factory: sessionmaker,
    settings: Settings,
    i18n_instance: JsonI18n,
) -> None:
    try:
        async with session_factory() as session:
            sync_result = await perform_sync(
                panel_service=panel_service,
                session=session,
                settings=settings,
                i18n_instance=i18n_instance,
            )
        status = sync_result.get("status")
        details = sync_result.get("details", "N/A")
        if status == "completed":
            logging.info(f"STARTUP: Background sync completed successfully. Details: {details}")
        elif status == "skipped":
            logging.info(f"STARTUP: Background sync skipped: {details}")
        else:
            logging.warning(
                f"STARTUP: Background sync finished with status '{status}'. Details: {details}"
            )
    except Exception:
        logging.exception("STARTUP: Background sync failed.")


async def on_shutdown_configured(dispatcher: Dispatcher):
    logging.warning("SHUTDOWN: on_shutdown_configured executing...")

    async def close_service(key: str) -> None:
        service = dispatcher.get(key)
        if not service:
            return
        close_coro = getattr(service, "close", None)
        if callable(close_coro):
            try:
                await close_coro()
                logging.info(f"{key} closed on shutdown.")
            except Exception as e:
                logging.warning(f"Failed to close {key}: {e}")
        else:
            close_session = getattr(service, "close_session", None)
            if callable(close_session):
                try:
                    await close_session()
                    logging.info(f"{key} session closed on shutdown.")
                except Exception as e:
                    logging.warning(f"Failed to close session for {key}: {e}")

    from bot.payment_providers import iter_service_keys

    for service_key in (
        "panel_service",
        "panel_webhook_service",
        "lknpd_service",
        "promo_code_service",
        "subscription_service",
        "referral_service",
        *iter_service_keys(),
    ):
        await close_service(service_key)

    bot: Bot = dispatcher["bot_instance"]
    if bot and bot.session:
        try:
            await bot.session.close()
            logging.info("SHUTDOWN: Aiogram Bot session closed.")
        except Exception as e:
            logging.warning(f"SHUTDOWN: Failed to close bot session: {e}")

    from db.database_setup import async_engine as global_async_engine

    if global_async_engine:
        logging.info("SHUTDOWN: Disposing SQLAlchemy engine...")
        await global_async_engine.dispose()
        logging.info("SHUTDOWN: SQLAlchemy engine disposed.")
    await close_redis()

    logging.info("SHUTDOWN: Bot on_shutdown_configured completed.")


async def run_bot(settings_param: Settings):
    local_async_session_factory = init_db_connection(settings_param)
    if local_async_session_factory is None:
        logging.critical("Failed to initialize database connection and session factory. Exiting.")
        return
    await load_overrides_from_db(settings_param, local_async_session_factory)
    dp, bot, extra = build_dispatcher(settings_param, local_async_session_factory)
    i18n_instance = extra["i18n_instance"]

    # Get bot username for YooKassa default return URL if needed
    actual_bot_username = "your_bot_username"
    try:
        bot_info = await bot.get_me()
        if bot_info.username:
            actual_bot_username = bot_info.username
            dp["bot_username"] = actual_bot_username
            logging.info(f"Bot username resolved: @{actual_bot_username}")
        else:
            logging.warning("Bot username is empty; Telegram Login Widget will be unavailable.")
    except Exception as e:
        logging.error(
            f"Failed to get bot info (e.g., for YooKassa default URL): {e}. Using fallback: {actual_bot_username}"  # noqa: E501
        )

    services = build_core_services(
        settings_param,
        bot,
        local_async_session_factory,
        i18n_instance,
        actual_bot_username,
    )
    for key, service in services.items():
        dp[key] = service
    dp["panel_service"] = services["panel_service"]
    dp["async_session_factory"] = local_async_session_factory

    # Wrap startup/shutdown handlers to satisfy aiogram event signature (no args passed)
    async def _on_startup_wrapper():
        await on_startup_configured(dp)

    async def _on_shutdown_wrapper():
        await on_shutdown_configured(dp)

    dp.startup.register(_on_startup_wrapper)
    dp.shutdown.register(_on_shutdown_wrapper)

    await register_all_routers(dp, settings_param)

    if not settings_param.WEBHOOK_BASE_URL:
        logging.error("WEBHOOK_BASE_URL is required. Polling mode is disabled. Exiting.")
        await dp.emit_shutdown()
        raise SystemExit("WEBHOOK_BASE_URL is required. Polling mode is disabled.")

    logging.info(
        "Starting AIOHTTP server: webhook_base=%s yookassa_path=%s",
        settings_param.WEBHOOK_BASE_URL,
        settings_param.yookassa_webhook_path,
    )

    async def web_server_task():
        await build_and_start_web_app(dp, bot, settings_param, local_async_session_factory)

    main_tasks = [asyncio.create_task(web_server_task(), name="AIOHTTPServerTask")]

    try:
        await asyncio.gather(*main_tasks)
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError) as e:
        logging.info(f"Main bot loop interrupted/cancelled: {type(e).__name__} - {e}")
    finally:
        logging.info("Initiating final bot shutdown sequence...")
        for task in main_tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logging.info(f"Task '{task.get_name()}' was cancelled successfully.")
                except Exception as e_task_cancel:
                    logging.error(
                        f"Error during cancellation of task '{task.get_name()}': {e_task_cancel}",
                        exc_info=True,
                    )

        await dp.emit_shutdown()
        logging.info("Dispatcher shutdown sequence emitted.")

        logging.info("Bot run_bot function finished.")
