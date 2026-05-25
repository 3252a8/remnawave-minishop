import asyncio
import logging
import sys
import time

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv
from startup_banner import print_startup_banner

import db.database_setup as database_setup
from app_logging import configure_logging
from bot.app.factories.build_services import build_core_services
from bot.handlers.admin.sync_admin import perform_sync
from bot.infra.redis import close_redis, redis_lock
from bot.infra.webhook_queue import pop_webhook_event, webhook_queue_depth
from bot.middlewares.i18n import get_i18n_instance
from bot.payment_providers.yookassa import (
    YOOKASSA_EVENT_PAYMENT_CANCELED,
    YOOKASSA_EVENT_PAYMENT_SUCCEEDED,
    payment_processing_lock,
    process_cancelled_payment,
    process_successful_payment,
)
from bot.services.locale_override_service import load_locale_overrides
from bot.services.settings_override_service import load_overrides_from_db
from bot.services.tariff_worker import TariffTrafficWorker
from bot.utils.message_queue import init_queue_manager
from config.settings import get_settings


async def _build_worker_context(settings):
    session_factory = database_setup.init_db_connection(settings)
    await load_overrides_from_db(settings, session_factory)
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    i18n = get_i18n_instance(path="locales", default=settings.DEFAULT_LANGUAGE)
    await load_locale_overrides(i18n, session_factory)
    bot_username = "your_bot_username"
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username or bot_username
    except Exception:
        logging.exception("Worker failed to resolve bot username")
    services = build_core_services(settings, bot, session_factory, i18n, bot_username)
    init_queue_manager(bot)
    return session_factory, bot, i18n, services


async def _webhook_consumer(settings, session_factory, bot, i18n, services):
    while True:
        event = await pop_webhook_event(settings)
        if not event:
            continue
        provider = event.get("provider")
        payload = event.get("payload") or {}
        started = time.monotonic()
        try:
            if provider == "yookassa":
                payment_payload = payload.get("payment") or {}
                async with payment_processing_lock:
                    async with session_factory() as session:
                        if payload.get("event") == YOOKASSA_EVENT_PAYMENT_SUCCEEDED:
                            await process_successful_payment(
                                session,
                                bot,
                                payment_payload,
                                i18n,
                                settings,
                                services["panel_service"],
                                services["subscription_service"],
                                services["referral_service"],
                                services.get("lknpd_service"),
                            )
                        elif payload.get("event") == YOOKASSA_EVENT_PAYMENT_CANCELED:
                            await process_cancelled_payment(
                                session,
                                bot,
                                payment_payload,
                                i18n,
                                settings,
                            )
                        await session.commit()
            elif provider == "panel":
                await services["panel_webhook_service"].handle_event(
                    str(payload.get("event") or ""),
                    payload.get("user") or {},
                )
            elif provider == "panel_sync":
                sync_result = None
                async with redis_lock(
                    settings,
                    "panel-sync",
                    ttl_seconds=max(60, settings.WORKER_PANEL_SYNC_INTERVAL_SECONDS - 10),
                ) as acquired:
                    if acquired:
                        async with session_factory() as session:
                            sync_result = await perform_sync(
                                panel_service=services["panel_service"],
                                session=session,
                                settings=settings,
                                i18n_instance=i18n,
                            )
                    else:
                        logging.info(
                            "Queued panel sync skipped because another sync holds the lock"
                        )
                if sync_result is not None:
                    await _notify_queued_panel_sync_result(
                        bot,
                        settings,
                        i18n,
                        payload,
                        sync_result,
                    )
            else:
                logging.warning("Unknown webhook event provider: %s", provider)
        except Exception:
            logging.exception("Webhook queue event failed: %s", event.get("event_id"))
        finally:
            depth = await webhook_queue_depth(settings)
            logging.info(
                "metric webhook_event_duration_seconds=%.3f provider=%s queue_depth=%s",
                time.monotonic() - started,
                provider,
                depth,
            )


async def _notify_queued_panel_sync_result(bot, settings, i18n, payload, sync_result):
    status = sync_result.get("status")
    errors = sync_result.get("errors", [])
    lang = payload.get("language") or settings.DEFAULT_LANGUAGE
    _ = lambda key, **kwargs: i18n.gettext(lang, key, **kwargs)

    target_chat_id = payload.get("target_chat_id")
    if target_chat_id:
        try:
            if status == "failed":
                await bot.send_message(target_chat_id, _("sync_failed_simple"))
            elif status == "completed_with_errors":
                await bot.send_message(
                    target_chat_id,
                    _("sync_errors_simple", errors_count=len(errors)),
                )
            else:
                await bot.send_message(target_chat_id, _("sync_success_simple"))
        except Exception:
            logging.exception("Failed to send queued panel sync result to admin")


async def _panel_sync_loop(settings, session_factory, i18n, services):
    while True:
        try:
            async with redis_lock(
                settings,
                "panel-sync",
                ttl_seconds=max(60, settings.WORKER_PANEL_SYNC_INTERVAL_SECONDS - 10),
            ) as acquired:
                if acquired:
                    started = time.monotonic()
                    async with session_factory() as session:
                        await perform_sync(
                            panel_service=services["panel_service"],
                            session=session,
                            settings=settings,
                            i18n_instance=i18n,
                        )
                    logging.info(
                        "metric worker_tick_duration_seconds=%.3f worker=panel_sync",
                        time.monotonic() - started,
                    )
        except Exception:
            logging.exception("Panel sync worker tick failed")
        await asyncio.sleep(settings.WORKER_PANEL_SYNC_INTERVAL_SECONDS)


async def main() -> None:
    settings = get_settings()
    session_factory, bot, i18n, services = await _build_worker_context(settings)
    tariff_worker = TariffTrafficWorker(
        settings,
        session_factory,
        services["panel_service"],
        services["subscription_service"],
        bot,
        i18n,
    )
    tasks = []
    if settings.tariffs_config:
        tasks.append(asyncio.create_task(tariff_worker.run(), name="TariffTrafficWorker"))
    tasks.append(asyncio.create_task(_panel_sync_loop(settings, session_factory, i18n, services)))
    for idx in range(max(1, settings.WEBHOOK_QUEUE_CONCURRENCY)):
        tasks.append(
            asyncio.create_task(
                _webhook_consumer(settings, session_factory, bot, i18n, services),
                name=f"WebhookConsumer{idx + 1}",
            )
        )
    try:
        await asyncio.gather(*tasks)
    finally:
        for service in services.values():
            close = getattr(service, "close", None) or getattr(service, "close_session", None)
            if callable(close):
                await close()
        await bot.session.close()
        await close_redis()
        if database_setup.async_engine:
            await database_setup.async_engine.dispose()


if __name__ == "__main__":
    load_dotenv()
    print_startup_banner("worker")
    configure_logging()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Worker stopped")
    except Exception as exc:
        logging.critical("Worker failed: %s", exc, exc_info=True)
        sys.exit(1)
