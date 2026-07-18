import asyncio
import logging
import sys
import time
from collections.abc import Coroutine
from typing import Any

from aiogram import Bot
from dotenv import load_dotenv
from startup_banner import print_startup_banner

import db.database_setup as database_setup
from app_logging import configure_logging
from bot.app.factories.runtime import build_core_runtime, build_runtime_bootstrap
from bot.handlers.admin.sync_admin import perform_sync
from bot.infra import events
from bot.infra.event_payloads import PaymentCanceledPayload
from bot.infra.observability import report_error
from bot.infra.redis import close_redis, redis_lock
from bot.infra.webhook_queue import (
    acknowledge_webhook_event,
    dead_letter_webhook_event,
    pop_webhook_event,
    recover_webhook_events,
    retry_webhook_event,
    webhook_queue_depth,
)
from bot.middlewares.i18n import JsonI18n
from bot.payment_providers.yookassa import (
    YOOKASSA_EVENT_PAYMENT_CANCELED,
    YOOKASSA_EVENT_PAYMENT_SUCCEEDED,
    emit_yookassa_success_events,
    payment_processing_lock,
    process_cancelled_payment,
    process_successful_payment,
)
from bot.payment_providers.yookassa.service import YooKassaService
from bot.plugins import (
    PluginContext,
    QueueHandler,
    WorkerTaskSpec,
    collect_queue_handlers,
    collect_worker_tasks,
    run_setup,
)
from bot.services.backup_worker import BackupWorker
from bot.services.event_reactions import register_core_reactions
from bot.services.message_log_notifier import configure_message_log_notifier
from bot.services.settings_override_service import refresh_overrides_from_db
from bot.services.subscription_notification_worker import SubscriptionNotificationWorker
from bot.services.tariff_worker import TariffTrafficWorker
from bot.services.torrent_blocker_webhook import TORRENT_BLOCKER_EVENT
from bot.services.yookassa_reconciliation_worker import YooKassaReconciliationWorker
from bot.utils.message_queue import init_queue_manager
from config.settings import Settings, get_settings

logger = logging.getLogger(__name__)

TORRENT_BLOCKER_RUNTIME_SETTING_KEYS = {
    "TORRENT_BLOCKER_EMAIL_NOTIFICATIONS_ENABLED",
    "TORRENT_BLOCKER_NOTIFICATIONS_ENABLED",
    "TORRENT_BLOCKER_NOTIFICATION_COOLDOWN_SECONDS",
    "TORRENT_BLOCKER_NOTIFICATION_INCLUDE_IP",
    "TORRENT_BLOCKER_TELEGRAM_NOTIFICATIONS_ENABLED",
}


async def _build_worker_context(settings: Settings) -> PluginContext:
    runtime = await build_runtime_bootstrap(settings)
    configure_message_log_notifier(settings, runtime.bot)
    bot_username = "your_bot_username"
    try:
        bot_info = await runtime.bot.get_me()
        bot_username = bot_info.username or bot_username
    except Exception:
        logger.exception("Worker failed to resolve bot username")
    init_queue_manager(runtime.bot)
    ctx = build_core_runtime(runtime, bot_username=bot_username).plugin_context
    run_setup(ctx)
    register_core_reactions(ctx)
    return ctx


async def _handle_yookassa_event(ctx: PluginContext, payload: dict[str, Any]) -> None:
    payment_payload = payload.get("payment") or {}
    session_factory = ctx.require_session_factory()
    bot = ctx.require_bot()
    i18n = ctx.require_i18n()
    async with payment_processing_lock, session_factory() as session:
        if payload.get("event") == YOOKASSA_EVENT_PAYMENT_SUCCEEDED:
            event_payload = await process_successful_payment(
                session,
                bot,
                payment_payload,
                i18n,
                ctx.settings,
                ctx.require_panel_service(),
                ctx.require_subscription_service(),
                ctx.require_referral_service(),
                ctx.lknpd_service,
            )
            await session.commit()
            if event_payload:
                await emit_yookassa_success_events(event_payload)
        elif payload.get("event") == YOOKASSA_EVENT_PAYMENT_CANCELED:
            event_payload = await process_cancelled_payment(
                session,
                bot,
                payment_payload,
                i18n,
                ctx.settings,
            )
            await session.commit()
            if event_payload:
                await events.emit_model(
                    PaymentCanceledPayload.model_validate(event_payload),
                    exclude_unset=True,
                )


async def _handle_panel_event(ctx: PluginContext, payload: dict[str, Any]) -> None:
    meta = payload.get("meta")
    context = payload.get("context")
    service = ctx.require_panel_webhook_service()
    event_name = str(payload.get("event") or "")
    if event_name == TORRENT_BLOCKER_EVENT:
        await refresh_overrides_from_db(
            ctx.settings,
            ctx.require_session_factory(),
            keys=TORRENT_BLOCKER_RUNTIME_SETTING_KEYS,
        )
    if isinstance(context, dict):
        await service.handle_event(
            event_name,
            payload.get("user") or {},
            meta=meta if isinstance(meta, dict) else None,
            context=context,
        )
    else:
        await service.handle_event(
            event_name,
            payload.get("user") or {},
            meta=meta if isinstance(meta, dict) else None,
        )


async def _handle_panel_sync_event(ctx: PluginContext, payload: dict[str, Any]) -> None:
    settings = ctx.settings
    session_factory = ctx.require_session_factory()
    bot = ctx.require_bot()
    i18n = ctx.require_i18n()
    sync_result = None
    async with redis_lock(
        settings,
        "panel-sync",
        ttl_seconds=max(60, settings.WORKER_PANEL_SYNC_INTERVAL_SECONDS - 10),
    ) as acquired:
        if acquired:
            async with session_factory() as session:
                sync_result = await perform_sync(
                    panel_service=ctx.require_panel_service(),
                    session=session,
                    settings=settings,
                    i18n_instance=i18n,
                )
        else:
            logger.info("Queued panel sync skipped because another sync holds the lock")
    if sync_result is not None:
        await _notify_queued_panel_sync_result(
            bot,
            settings,
            i18n,
            payload,
            sync_result,
        )


def _core_queue_handlers() -> dict[str, QueueHandler]:
    return {
        "yookassa": _handle_yookassa_event,
        "panel": _handle_panel_event,
        "panel_sync": _handle_panel_sync_event,
    }


def _webhook_delivery_attempts(event: dict[str, Any]) -> int:
    try:
        return max(0, int(event.get("delivery_attempts") or 0))
    except (TypeError, ValueError):
        return 0


def _webhook_retry_delay(settings: Settings, delivery_attempts: int) -> float:
    delay = settings.WEBHOOK_QUEUE_RETRY_BASE_SECONDS * (2 ** max(0, delivery_attempts - 1))
    return min(delay, settings.WEBHOOK_QUEUE_RETRY_MAX_SECONDS)


async def _webhook_consumer(ctx: PluginContext, handlers: dict[str, QueueHandler]) -> None:
    settings = ctx.settings
    while True:
        claimed = await pop_webhook_event(settings)
        if not claimed:
            continue
        event = claimed.event
        provider = event.get("provider")
        payload = event.get("payload") or {}
        started = time.monotonic()
        try:
            handler = handlers.get(str(provider))
            if handler is None:
                raise LookupError(f"Unknown webhook event provider: {provider}")
            await handler(ctx, payload)
            if not await acknowledge_webhook_event(settings, claimed):
                logger.warning(
                    "Webhook queue event %s completed but could not be acknowledged",
                    event.get("event_id"),
                )
        except Exception as exc:
            logger.exception("Webhook queue event failed: %s", event.get("event_id"))
            await report_error(
                ctx.error_reporter,
                exc,
                source="worker.webhook_consumer",
                attributes={
                    "event_id": event.get("event_id"),
                    "provider": str(provider),
                },
            )
            delivery_attempts = _webhook_delivery_attempts(event) + 1
            if delivery_attempts >= settings.WEBHOOK_QUEUE_MAX_ATTEMPTS:
                moved = await dead_letter_webhook_event(
                    settings,
                    claimed,
                    delivery_attempts=delivery_attempts,
                    error=exc,
                )
                if moved:
                    logger.error(
                        "Webhook queue event %s moved to dead-letter after %s attempt(s)",
                        event.get("event_id"),
                        delivery_attempts,
                    )
                else:
                    logger.error(
                        "Webhook queue event %s exhausted retries but could not be dead-lettered",
                        event.get("event_id"),
                    )
            else:
                delay = _webhook_retry_delay(settings, delivery_attempts)
                if delay:
                    await asyncio.sleep(delay)
                moved = await retry_webhook_event(
                    settings,
                    claimed,
                    delivery_attempts=delivery_attempts,
                )
                if moved:
                    logger.warning(
                        "Webhook queue event %s scheduled for retry %s/%s",
                        event.get("event_id"),
                        delivery_attempts + 1,
                        settings.WEBHOOK_QUEUE_MAX_ATTEMPTS,
                    )
                else:
                    logger.error(
                        "Webhook queue event %s could not be requeued",
                        event.get("event_id"),
                    )
        finally:
            depth = await webhook_queue_depth(settings)
            logger.info(
                "metric webhook_event_duration_seconds=%.3f provider=%s queue_depth=%s",
                time.monotonic() - started,
                provider,
                depth,
            )


async def _notify_queued_panel_sync_result(
    bot: Bot,
    settings: Settings,
    i18n: JsonI18n,
    payload: dict[str, Any],
    sync_result: dict[str, Any],
) -> None:
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
            logger.exception("Failed to send queued panel sync result to admin")


async def _panel_sync_loop(ctx: PluginContext) -> None:
    settings = ctx.settings
    session_factory = ctx.require_session_factory()
    i18n = ctx.require_i18n()
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
                            panel_service=ctx.require_panel_service(),
                            session=session,
                            settings=settings,
                            i18n_instance=i18n,
                        )
                    logger.info(
                        "metric worker_tick_duration_seconds=%.3f worker=panel_sync",
                        time.monotonic() - started,
                    )
        except Exception as exc:
            logger.exception("Panel sync worker tick failed")
            await report_error(
                ctx.error_reporter,
                exc,
                source="worker.panel_sync",
                attributes={"worker": "panel_sync"},
            )
        await asyncio.sleep(settings.WORKER_PANEL_SYNC_INTERVAL_SECONDS)


def _tariff_worker_task(ctx: PluginContext) -> Coroutine[Any, Any, None]:
    return TariffTrafficWorker(
        ctx.settings,
        ctx.require_session_factory(),
        ctx.require_panel_service(),
        ctx.require_subscription_service(),
        ctx.require_bot(),
        ctx.require_i18n(),
    ).run()


def _subscription_notification_task(ctx: PluginContext) -> Coroutine[Any, Any, None]:
    return SubscriptionNotificationWorker(
        ctx.settings,
        ctx.require_session_factory(),
        ctx.require_bot(),
        ctx.require_i18n(),
        ctx.require_panel_service(),
        ctx.require_subscription_service(),
    ).run()


async def _yookassa_reconciliation_task(ctx: PluginContext) -> None:
    yookassa_service = ctx.get_service("yookassa_service", YooKassaService)
    if yookassa_service is None:
        logger.info("YooKassa reconciliation worker disabled: service is unavailable")
        return
    await YooKassaReconciliationWorker(
        ctx.settings,
        ctx.require_session_factory(),
        yookassa_service,
        ctx.require_bot(),
        ctx.require_i18n(),
        ctx.require_panel_service(),
        ctx.require_subscription_service(),
        ctx.require_referral_service(),
        ctx.lknpd_service,
    ).run()


def _backup_worker_task(ctx: PluginContext) -> Coroutine[Any, Any, None]:
    return BackupWorker(
        ctx.settings,
        ctx.require_bot(),
        session_factory=ctx.require_session_factory(),
    ).run()


def _core_worker_tasks() -> list[WorkerTaskSpec]:
    return [
        WorkerTaskSpec(
            name="TariffTrafficWorker",
            factory=_tariff_worker_task,
            enabled=lambda settings: bool(settings.tariffs_config),
        ),
        WorkerTaskSpec(
            name="SubscriptionNotificationWorker",
            factory=_subscription_notification_task,
        ),
        WorkerTaskSpec(
            name="YooKassaReconciliationWorker",
            factory=_yookassa_reconciliation_task,
        ),
        WorkerTaskSpec(name="BackupWorker", factory=_backup_worker_task),
        WorkerTaskSpec(name="PanelSyncLoop", factory=_panel_sync_loop),
    ]


async def main() -> None:
    settings = get_settings()
    ctx = await _build_worker_context(settings)

    recovered = await recover_webhook_events(settings)
    if recovered:
        logger.warning("Recovered %s unacknowledged webhook queue event(s)", recovered)

    handlers = _core_queue_handlers()
    handlers.update(collect_queue_handlers(ctx, reserved=set(handlers)))

    task_specs = [*_core_worker_tasks(), *collect_worker_tasks(ctx)]
    tasks = []
    for spec in task_specs:
        if spec.enabled is not None and not spec.enabled(settings):
            continue
        tasks.append(asyncio.create_task(spec.factory(ctx), name=spec.name))
    tasks.extend(
        asyncio.create_task(
            _webhook_consumer(ctx, handlers),
            name=f"WebhookConsumer{idx + 1}",
        )
        for idx in range(max(1, settings.WEBHOOK_QUEUE_CONCURRENCY))
    )
    try:
        await asyncio.gather(*tasks)
    finally:
        for service in ctx.services.values():
            close = getattr(service, "close", None) or getattr(service, "close_session", None)
            if callable(close):
                await close()
        await ctx.require_bot().session.close()
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
        logger.info("Worker stopped")
    except Exception as exc:
        logger.critical("Worker failed: %s", exc, exc_info=True)
        sys.exit(1)
