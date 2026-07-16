import asyncio
import logging
from collections.abc import Awaitable, Callable

from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
    BotCommandScopeUnion,
    MenuButtonDefault,
    MenuButtonWebApp,
    WebAppInfo,
)

from bot.app.controllers.dispatcher_context import (
    get_dispatcher_bot,
    get_dispatcher_i18n,
    get_dispatcher_service,
    get_dispatcher_settings,
    set_dispatcher_bot_username,
    set_dispatcher_queue_manager,
    set_dispatcher_services,
)
from bot.app.controllers.dispatcher_controller import build_dispatcher
from bot.app.factories.runtime import build_core_runtime, build_runtime_bootstrap
from bot.app.web.web_server import build_and_start_web_app
from bot.infra.redis import close_redis
from bot.plugins import PluginContext, run_setup
from bot.routers import build_root_router
from bot.services.event_reactions import register_core_reactions
from bot.services.message_log_notifier import configure_message_log_notifier
from bot.utils.message_queue import init_queue_manager
from config.settings import Settings

logger = logging.getLogger(__name__)

TELEGRAM_STARTUP_RETRY_DELAY_SECONDS = 2.0


def _telegram_command_language_codes(settings: Settings) -> list[str | None]:
    language_codes: list[str | None] = [None]
    for code in (settings.DEFAULT_LANGUAGE, "ru", "en"):
        normalized = str(code or "").strip().lower()
        if normalized and normalized not in language_codes:
            language_codes.append(normalized)
    return language_codes


def redact_token(value: str, token: str | None) -> str:
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
    attempts: int | None = None,
    retry_delay_seconds: float = TELEGRAM_STARTUP_RETRY_DELAY_SECONDS,
) -> bool:
    attempt = 1
    max_attempts = max(1, attempts) if attempts is not None else None
    while True:
        try:
            await step()
            if attempt > 1:
                logger.info(
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
                logger.warning(
                    "STARTUP: Telegram network error while %s after %s attempts: %s.",
                    action,
                    max_attempts,
                    detail,
                )
                return False
            logger.warning(
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
            logger.exception(unexpected_log_message)
            return False


async def register_all_routers(
    dp: Dispatcher,
    settings: Settings,
    plugin_context: PluginContext | None = None,
):
    dp.include_router(build_root_router(settings, plugin_context))
    logger.info("All application routers registered.")


async def configure_telegram_webhook(dispatcher: Dispatcher) -> None:
    bot = get_dispatcher_bot(dispatcher)
    settings = get_dispatcher_settings(dispatcher)

    telegram_webhook_url_to_set = settings.WEBHOOK_BASE_URL
    if telegram_webhook_url_to_set:
        full_telegram_webhook_url = (
            f"{str(telegram_webhook_url_to_set).rstrip('/')}{settings.telegram_webhook_path}"
        )

        logger.info(
            "STARTUP: Attempting to set Telegram webhook to: %s",
            redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
        )

        async def _configure_webhook() -> None:
            current_webhook_info = await bot.get_webhook_info()
            logger.info(
                "STARTUP: Current Telegram webhook info BEFORE setting: %s",
                current_webhook_info.model_dump_json(exclude_none=True, indent=2),
            )

            set_success = await bot.set_webhook(
                url=full_telegram_webhook_url,
                secret_token=settings.WEBHOOK_SECRET_TOKEN,
                drop_pending_updates=True,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
            if set_success:
                logger.info(
                    "STARTUP: bot.set_webhook to %s returned SUCCESS (True).",
                    redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
                )
            else:
                logger.error(
                    "STARTUP: bot.set_webhook to %s returned FAILURE (False).",
                    redact_token(full_telegram_webhook_url, settings.BOT_TOKEN),
                )

            new_webhook_info = await bot.get_webhook_info()
            logger.info(
                "STARTUP: Telegram Webhook info AFTER setting: %s",
                new_webhook_info.model_dump_json(exclude_none=True, indent=2),
            )
            if not new_webhook_info.url:
                logger.error(
                    "STARTUP: CRITICAL - Telegram Webhook URL is EMPTY after set attempt. Check bot token and URL validity."  # noqa: E501
                )

        await _run_telegram_startup_step(
            "configuring Telegram webhook",
            _configure_webhook,
            "STARTUP: EXCEPTION during set/get Telegram webhook.",
        )
    else:
        logger.error(
            "STARTUP: WEBHOOK_BASE_URL not set in environment. Webhook mode is required. Exiting."
        )
        raise SystemExit("WEBHOOK_BASE_URL is required. Polling mode is disabled.")


async def on_startup_configured(dispatcher: Dispatcher):
    bot = get_dispatcher_bot(dispatcher)
    settings = get_dispatcher_settings(dispatcher)
    i18n_instance = get_dispatcher_i18n(dispatcher)

    logger.info("STARTUP: on_startup_configured executing...")

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
            logger.info("STARTUP: Mini app domain registered and default menu button restored.")

        await _run_telegram_startup_step(
            "registering mini app menu button",
            _configure_mini_app_menu,
            "STARTUP: Failed to register mini app domain.",
        )

    async def _configure_bot_commands() -> None:
        start_description = settings.START_COMMAND_DESCRIPTION or "Main menu"
        bot_commands = [
            BotCommand(command="start", description=start_description),
            BotCommand(command="tg", description="Bot interface"),
        ]
        bot_menu_disabled = bool(settings.TELEGRAM_BOT_MENU_DISABLED)
        public_bot_commands = [bot_commands[0]] if bot_menu_disabled else bot_commands
        command_scopes_to_clear: list[BotCommandScopeUnion] = [
            BotCommandScopeDefault(),
            BotCommandScopeAllPrivateChats(),
            BotCommandScopeAllGroupChats(),
            BotCommandScopeAllChatAdministrators(),
        ]
        for scope in command_scopes_to_clear:
            for language_code in _telegram_command_language_codes(settings):
                await bot.delete_my_commands(scope=scope, language_code=language_code)
        if bot_menu_disabled:
            for admin_id in settings.ADMIN_IDS or []:
                for language_code in _telegram_command_language_codes(settings):
                    try:
                        await bot.delete_my_commands(
                            scope=BotCommandScopeChat(chat_id=admin_id),
                            language_code=language_code,
                        )
                    except TelegramBadRequest as exc:
                        logger.warning(
                            "STARTUP: Could not clear chat-specific bot commands for chat %s: %s",
                            admin_id,
                            exc,
                        )
        await bot.set_my_commands(public_bot_commands, scope=BotCommandScopeDefault())
        await bot.set_my_commands(public_bot_commands, scope=BotCommandScopeAllPrivateChats())
        logger.info("STARTUP: bot command descriptions set.")

    await _run_telegram_startup_step(
        "setting bot commands",
        _configure_bot_commands,
        "STARTUP: Failed to set bot commands.",
    )

    # Initialize message queue manager
    try:
        queue_manager = init_queue_manager(bot)
        set_dispatcher_queue_manager(dispatcher, queue_manager)
        logger.info("STARTUP: Message queue manager initialized")
    except Exception:
        logger.exception("STARTUP: Failed to initialize message queue manager.")

    logger.info("STARTUP: Bot on_startup_configured completed.")


async def on_shutdown_configured(dispatcher: Dispatcher):
    logger.warning("SHUTDOWN: on_shutdown_configured executing...")

    async def close_service(key: str) -> None:
        service = get_dispatcher_service(dispatcher, key)
        if not service:
            return
        close_coro = getattr(service, "close", None)
        if callable(close_coro):
            try:
                await close_coro()
                logger.info("%s closed on shutdown.", key)
            except Exception as e:
                logger.warning("Failed to close %s: %s", key, e)
        else:
            close_session = getattr(service, "close_session", None)
            if callable(close_session):
                try:
                    await close_session()
                    logger.info("%s session closed on shutdown.", key)
                except Exception as e:
                    logger.warning("Failed to close session for %s: %s", key, e)

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

    bot = get_dispatcher_bot(dispatcher)
    if bot and bot.session:
        try:
            await bot.session.close()
            logger.info("SHUTDOWN: Aiogram Bot session closed.")
        except Exception as e:
            logger.warning("SHUTDOWN: Failed to close bot session: %s", e)

    from db.database_setup import async_engine as global_async_engine

    if global_async_engine:
        logger.info("SHUTDOWN: Disposing SQLAlchemy engine...")
        await global_async_engine.dispose()
        logger.info("SHUTDOWN: SQLAlchemy engine disposed.")
    await close_redis()

    logger.info("SHUTDOWN: Bot on_shutdown_configured completed.")


async def run_bot(settings_param: Settings):
    runtime = await build_runtime_bootstrap(settings_param)
    bot = runtime.bot
    configure_message_log_notifier(settings_param, bot)
    i18n_instance = runtime.i18n
    local_async_session_factory = runtime.session_factory
    dp = build_dispatcher(
        settings_param,
        local_async_session_factory,
        bot=bot,
        i18n_instance=i18n_instance,
    )

    # Get bot username for YooKassa default return URL if needed
    actual_bot_username = "your_bot_username"

    async def _resolve_bot_username() -> None:
        nonlocal actual_bot_username
        bot_info = await bot.get_me()
        if bot_info.username:
            actual_bot_username = bot_info.username
            set_dispatcher_bot_username(dp, actual_bot_username)
            logger.info("Bot username resolved: @%s", actual_bot_username)
        else:
            logger.warning("Bot username is empty; Telegram Login Widget will be unavailable.")

    bot_username_resolved = await _run_telegram_startup_step(
        "getting bot info from Telegram",
        _resolve_bot_username,
        f"Failed to get bot info (e.g., for YooKassa default URL). Using fallback: {actual_bot_username}",  # noqa: E501
    )
    if not bot_username_resolved:
        logger.warning("Using fallback bot username: %s", actual_bot_username)

    core_runtime = build_core_runtime(runtime, bot_username=actual_bot_username, dispatcher=dp)
    plugin_context = core_runtime.plugin_context
    services = core_runtime.services
    # Plugins may contribute services, so run setup before the dispatcher copy.
    run_setup(plugin_context)
    register_core_reactions(plugin_context)

    set_dispatcher_services(dp, services)

    # Wrap startup/shutdown handlers to satisfy aiogram event signature (no args passed)
    async def _on_startup_wrapper():
        await on_startup_configured(dp)

    async def _on_shutdown_wrapper():
        await on_shutdown_configured(dp)

    dp.startup.register(_on_startup_wrapper)
    dp.shutdown.register(_on_shutdown_wrapper)

    await register_all_routers(dp, settings_param, plugin_context)

    if not settings_param.WEBHOOK_BASE_URL:
        logger.error("WEBHOOK_BASE_URL is required. Polling mode is disabled. Exiting.")
        await dp.emit_shutdown()
        raise SystemExit("WEBHOOK_BASE_URL is required. Polling mode is disabled.")

    from bot.payment_providers import get_provider_spec

    _yk_spec = get_provider_spec("yookassa")
    _yk_path = _yk_spec.webhook_path(settings_param) if _yk_spec and _yk_spec.webhook_path else "-"
    logger.info(
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
        logger.info("Main bot loop interrupted/cancelled: %s - %s", type(e).__name__, e)
    finally:
        logger.info("Initiating final bot shutdown sequence...")
        for task in main_tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    logger.info("Task '%s' was cancelled successfully.", task.get_name())
                except Exception as e_task_cancel:
                    logger.exception(
                        "Error during cancellation of task '%s': %s", task.get_name(), e_task_cancel
                    )

        await dp.emit_shutdown()
        logger.info("Dispatcher shutdown sequence emitted.")

        logger.info("Bot run_bot function finished.")
