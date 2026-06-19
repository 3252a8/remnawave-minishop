import asyncio
import logging
from typing import Awaitable, Callable, Optional

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
    MenuButtonDefault,
    MenuButtonWebApp,
    WebAppInfo,
)

from bot.app.controllers.dispatcher_controller import build_dispatcher
from bot.app.factories.build_services import build_core_services
from bot.app.web.web_server import build_and_start_web_app
from bot.infra.redis import close_redis
from bot.middlewares.i18n import JsonI18n
from bot.plugins import PluginContext, apply_plugin_locales, run_setup
from bot.routers import build_root_router
from bot.services.event_reactions import register_core_reactions
from bot.services.locale_override_service import load_locale_overrides
from bot.utils.message_queue import init_queue_manager
from config.settings import Settings
from db.database_setup import init_db, init_db_connection

TELEGRAM_STARTUP_RETRY_DELAY_SECONDS = 2.0


def _telegram_command_language_codes(settings: Settings) -> list[Optional[str]]:
    language_codes: list[Optional[str]] = [None]
    for code in (settings.DEFAULT_LANGUAGE, "ru", "en"):
        normalized = str(code or "").strip().lower()
        if normalized and normalized not in language_codes:
            language_codes.append(normalized)
    return language_codes


def redact_token(value: str, token: Optional[str]) -> str:
    if not value or not token:
        return value
    return value.replace(token, "***")


def _telegram_network_error_detail(exc: TelegramNetworkError) -> str:
    root_cause = exc.__cause__ or exc.__context__
    detail = str(exc)
    if root_cause:
        root_detail = f"{type(root_cause).__name__}: {root_cause}"
        if root_detail not in detail:
            detail = f"{detail} ({root_detail})"
    return detail


async def _run_telegram_startup_step(
    action: str,
    step: Callable[[], Awaitable[object]],
    unexpected_log_message: str,
    *,
    attempts: Optional[int] = None,
    retry_delay_seconds: float = TELEGRAM_STARTUP_RETRY_DELAY_SECONDS,
) -> bool:
    attempt = 1
    max_attempts = max(1, attempts) if attempts is not None else None
    while True:
        try:
            await step()
            if attempt > 1:
                logging.info(
                    "STARTUP: Telegram step succeeded while %s on attempt %s%s.",
                    action,
                    attempt,
                    f"/{max_attempts}" if max_attempts is not None else "",
                )
            return True
        except TelegramNetworkError as exc:
            detail = _telegram_network_error_detail(exc)
            attempt_label = (
                f"{attempt}/{max_attempts}" if max_attempts is not None else str(attempt)
            )
            if max_attempts is not None and attempt >= max_attempts:
                logging.warning(
                    "STARTUP: Telegram network error while %s after %s attempts: %s.",
                    action,
                    max_attempts,
                    detail,
                )
                return False
            logging.warning(
                "STARTUP: Telegram network error while %s on attempt %s: %s. "
                "Retrying in %.1fs and will keep trying until Telegram is reachable.",
                action,
                attempt_label,
                detail,
                retry_delay_seconds,
            )
            attempt += 1
            await asyncio.sleep(retry_delay_seconds)
            continue
        except Exception:
            logging.exception(unexpected_log_message)
            return False


async def register_all_routers(
    dp: Dispatcher,
    settings: Settings,
    plugin_context: Optional[PluginContext] = None,
):
    dp.include_router(build_root_router(settings, plugin_context))
    logging.info("All application routers registered.")


async def configure_telegram_webhook(dispatcher: Dispatcher) -> None:
    bot: Bot = dispatcher["bot_instance"]
    settings: Settings = dispatcher["settings"]

    telegram_webhook_url_to_set = settings.WEBHOOK_BASE_URL
    if telegram_webhook_url_to_set:
        full_telegram_webhook_url = (
            f"{str(telegram_webhook_url_to_set).rstrip('/')}{settings.telegram_webhook_path}"
        )

        logging.info(
            "STARTUP: Attempting to set Telegram webhook to: %s",
            redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
        )

        async def _configure_webhook() -> None:
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

        await _run_telegram_startup_step(
            "configuring Telegram webhook",
            _configure_webhook,
            "STARTUP: EXCEPTION during set/get Telegram webhook.",
        )
    else:
        logging.error(
            "STARTUP: WEBHOOK_BASE_URL not set in environment. Webhook mode is required. Exiting."
        )
        raise SystemExit("WEBHOOK_BASE_URL is required. Polling mode is disabled.")


async def on_startup_configured(dispatcher: Dispatcher):
    bot: Bot = dispatcher["bot_instance"]
    settings: Settings = dispatcher["settings"]
    i18n_instance: JsonI18n = dispatcher["i18n_instance"]

    logging.info("STARTUP: on_startup_configured executing...")

    if settings.SUBSCRIPTION_MINI_APP_URL:

        async def _configure_mini_app_menu() -> None:
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

        await _run_telegram_startup_step(
            "registering mini app menu button",
            _configure_mini_app_menu,
            "STARTUP: Failed to register mini app domain.",
        )

    async def _configure_bot_commands() -> None:
        start_description = settings.START_COMMAND_DESCRIPTION or "Главное меню"
        bot_commands = [
            BotCommand(command="start", description=start_description),
            BotCommand(command="tg", description="Интерфейс в боте"),
        ]
        command_scopes_to_clear = [
            BotCommandScopeDefault(),
            BotCommandScopeAllPrivateChats(),
            BotCommandScopeAllGroupChats(),
            BotCommandScopeAllChatAdministrators(),
        ]
        for scope in command_scopes_to_clear:
            for language_code in _telegram_command_language_codes(settings):
                await bot.delete_my_commands(scope=scope, language_code=language_code)
        await bot.set_my_commands(bot_commands, scope=BotCommandScopeDefault())
        await bot.set_my_commands(bot_commands, scope=BotCommandScopeAllPrivateChats())
        logging.info("STARTUP: bot command descriptions set.")

    await _run_telegram_startup_step(
        "setting bot commands",
        _configure_bot_commands,
        "STARTUP: Failed to set bot commands.",
    )

    # Initialize message queue manager
    try:
        queue_manager = init_queue_manager(bot)
        dispatcher["queue_manager"] = queue_manager
        logging.info("STARTUP: Message queue manager initialized")
    except Exception:
        logging.exception("STARTUP: Failed to initialize message queue manager.")

    logging.info("STARTUP: Bot on_startup_configured completed.")


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
        "support_service",
        "notification_service",
        "email_auth_service",
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
    await init_db(settings_param, local_async_session_factory)
    dp, bot, extra = build_dispatcher(settings_param, local_async_session_factory)
    i18n_instance = extra["i18n_instance"]
    apply_plugin_locales(settings_param, i18n_instance)
    await load_locale_overrides(i18n_instance, local_async_session_factory)

    # Get bot username for YooKassa default return URL if needed
    actual_bot_username = "your_bot_username"

    async def _resolve_bot_username() -> None:
        nonlocal actual_bot_username
        bot_info = await bot.get_me()
        if bot_info.username:
            actual_bot_username = bot_info.username
            dp["bot_username"] = actual_bot_username
            logging.info(f"Bot username resolved: @{actual_bot_username}")
        else:
            logging.warning("Bot username is empty; Telegram Login Widget will be unavailable.")

    bot_username_resolved = await _run_telegram_startup_step(
        "getting bot info from Telegram",
        _resolve_bot_username,
        f"Failed to get bot info (e.g., for YooKassa default URL). Using fallback: {actual_bot_username}",  # noqa: E501
    )
    if not bot_username_resolved:
        logging.warning("Using fallback bot username: %s", actual_bot_username)

    services = build_core_services(
        settings_param,
        bot,
        local_async_session_factory,
        i18n_instance,
        actual_bot_username,
    )
    plugin_context = PluginContext(
        settings=settings_param,
        session_factory=local_async_session_factory,
        bot=bot,
        i18n=i18n_instance,
        dispatcher=dp,
        services=services,
    )
    # Plugins may contribute services, so run setup before the dispatcher copy.
    run_setup(plugin_context)
    register_core_reactions(plugin_context)

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

    await register_all_routers(dp, settings_param, plugin_context)

    if not settings_param.WEBHOOK_BASE_URL:
        logging.error("WEBHOOK_BASE_URL is required. Polling mode is disabled. Exiting.")
        await dp.emit_shutdown()
        raise SystemExit("WEBHOOK_BASE_URL is required. Polling mode is disabled.")

    from bot.payment_providers import get_provider_spec

    _yk_spec = get_provider_spec("yookassa")
    _yk_path = _yk_spec.webhook_path(settings_param) if _yk_spec and _yk_spec.webhook_path else "-"
    logging.info(
        "Starting AIOHTTP server: webhook_base=%s yookassa_path=%s",
        settings_param.WEBHOOK_BASE_URL,
        _yk_path,
    )

    async def _after_webhooks_started() -> None:
        await configure_telegram_webhook(dp)

    async def web_server_task():
        await build_and_start_web_app(
            dp,
            bot,
            settings_param,
            local_async_session_factory,
            after_webhooks_started=_after_webhooks_started,
            plugin_context=plugin_context,
        )

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
