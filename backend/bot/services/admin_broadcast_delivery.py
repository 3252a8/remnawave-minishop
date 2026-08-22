"""Durable delivery for immediate and scheduled admin broadcasts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from aiogram.types import FSInputFile
from sqlalchemy.orm import sessionmaker

from bot.middlewares.i18n import JsonI18n
from bot.services.audience_segmentation import AudienceSegmentationService
from bot.services.broadcast_email_service import (
    BroadcastEmailRecipient,
    schedule_broadcast_emails,
)
from bot.services.broadcast_personalization import (
    BroadcastUserContext,
    known_shortcodes,
    load_broadcast_contexts,
    render_broadcast_text,
)
from bot.services.message_composition import (
    MessageButton,
    MessageButtonInput,
    email_links_for_buttons,
    resolve_localized_text,
    resolve_message_buttons,
    telegram_markup_for_buttons,
)
from bot.services.message_image_service import StoredMessageImage, load_message_image
from bot.services.telegram_notifications import record_telegram_notification_failure
from bot.utils.message_queue import MessageQueueManager
from config.settings import Settings
from db.broadcast_models import AdminBroadcast, AdminBroadcastDelivery
from db.dal import broadcast_dal, user_dal

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_MAX_LENGTH = 4096


@dataclass(frozen=True)
class BroadcastDispatchResult:
    queued: int
    failed: int
    email_queued: int
    channels: list[str]


class AdminBroadcastDeliveryService:
    def __init__(
        self,
        *,
        settings: Settings,
        session_factory: sessionmaker,
        i18n: JsonI18n,
        audience_service: AudienceSegmentationService,
        queue_manager: MessageQueueManager | None,
        bot_username: str | None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.i18n = i18n
        self.audience_service = audience_service
        self.queue_manager = queue_manager
        self.bot_username = bot_username

    async def dispatch(
        self,
        broadcast_id: int,
        *,
        user_ids: list[int] | None = None,
    ) -> BroadcastDispatchResult:
        async with self.session_factory() as session:
            broadcast = await broadcast_dal.begin_broadcast(session, broadcast_id)
        if broadcast is None:
            return BroadcastDispatchResult(queued=0, failed=0, email_queued=0, channels=[])

        channels = [str(value) for value in list(broadcast.channels or [])]
        if "telegram" in channels and self.queue_manager is None:
            await self._fail_broadcast(broadcast_id, "queue_unavailable")
            raise RuntimeError("queue_unavailable")

        try:
            resolved_user_ids = user_ids
            if resolved_user_ids is None:
                resolved_user_ids = [
                    int(user_id)
                    for user_id in await self.audience_service.resolve_user_ids(
                        str(broadcast.target)
                    )
                ]
            deliveries = await self._prepare_deliveries(broadcast, resolved_user_ids, channels)
            if not deliveries:
                async with self.session_factory() as session:
                    await broadcast_dal.finish_empty_broadcast(session, broadcast_id)
                return BroadcastDispatchResult(0, 0, 0, channels)
            return await self._queue_deliveries(broadcast, deliveries, resolved_user_ids, channels)
        except Exception as exc:
            await self._fail_broadcast(broadcast_id, str(exc))
            raise

    async def _prepare_deliveries(
        self,
        broadcast: AdminBroadcast,
        user_ids: list[int],
        channels: list[str],
    ) -> list[AdminBroadcastDelivery]:
        payloads: list[dict[str, Any]] = []
        async with self.session_factory() as session:
            languages = await user_dal.get_language_codes_for_broadcast(session, user_ids)
            if "telegram" in channels:
                for user_id, chat_id in await user_dal.get_telegram_recipients_for_broadcast(
                    session,
                    user_ids,
                    exclude_blocked=bool(getattr(broadcast, "exclude_blocked_telegram", False)),
                ):
                    payloads.append(
                        {
                            "user_id": user_id,
                            "channel": "telegram",
                            "destination": str(chat_id),
                            "language_code": languages.get(user_id),
                        }
                    )
            if "email" in channels:
                for user_id, email, language in await user_dal.get_email_recipients_for_broadcast(
                    session, user_ids
                ):
                    payloads.append(
                        {
                            "user_id": user_id,
                            "channel": "email",
                            "destination": email,
                            "language_code": language or languages.get(user_id),
                        }
                    )
            return await broadcast_dal.add_deliveries(session, broadcast, payloads)

    async def _queue_deliveries(
        self,
        broadcast: AdminBroadcast,
        deliveries: list[AdminBroadcastDelivery],
        user_ids: list[int],
        channels: list[str],
    ) -> BroadcastDispatchResult:
        texts = {str(key): str(value) for key, value in dict(broadcast.texts or {}).items()}
        subjects = {
            str(key): str(value) for key, value in dict(broadcast.email_subjects or {}).items()
        }
        button_inputs = [
            MessageButtonInput(
                kind=str(item.get("kind") or "url"),
                label=str(item.get("label") or ""),
                url=str(item.get("url") or ""),
                promo_code=str(item.get("promo_code") or ""),
                section=str(item.get("section") or ""),
                labels={
                    str(key): str(value) for key, value in dict(item.get("labels") or {}).items()
                },
            )
            for item in list(broadcast.buttons or [])
            if isinstance(item, dict)
        ]
        authored_variants = [*texts.values(), *subjects.values()]
        needed = set().union(*(known_shortcodes(value) for value in authored_variants))
        contexts: dict[int, BroadcastUserContext] = {}
        stored_image: StoredMessageImage | None = None
        email_image = None
        image_id = getattr(broadcast, "image_id", None)
        if image_id:
            async with self.session_factory() as session:
                stored_image = await load_message_image(session, str(image_id))
            if stored_image is None or not stored_image.path.is_file():
                raise RuntimeError("image_missing")
            email_image = await stored_image.email_inline()
        if needed:
            async with self.session_factory() as session:
                contexts = await load_broadcast_contexts(
                    session,
                    self.settings,
                    user_ids,
                    needed,
                    self.audience_service.panel_service,
                )

        button_cache: dict[str, list[MessageButton]] = {}

        def language_for(delivery: AdminBroadcastDelivery) -> str:
            context = contexts.get(int(delivery.user_id))
            return str(
                (context.language_code if context else None)
                or delivery.language_code
                or self.settings.DEFAULT_LANGUAGE
            )

        def buttons_for(language: str) -> list[MessageButton]:
            if language not in button_cache:
                button_cache[language] = resolve_message_buttons(
                    button_inputs,
                    mini_app_url=self.settings.SUBSCRIPTION_MINI_APP_URL,
                    bot_username=self.bot_username,
                    language=language,
                    translate=lambda lang, key: self.i18n.gettext(lang, key),
                    default_language=self.settings.DEFAULT_LANGUAGE,
                )
            return button_cache[language]

        queued = 0
        failed = 0
        email_recipients: list[BroadcastEmailRecipient] = []
        for delivery in deliveries:
            language = language_for(delivery)
            template = resolve_localized_text(
                texts,
                language=language,
                default_language=self.settings.DEFAULT_LANGUAGE,
            )
            rendered = (
                render_broadcast_text(
                    template,
                    contexts.get(int(delivery.user_id)),
                    lang=language,
                    i18n=self.i18n,
                    settings=self.settings,
                    bot_username=self.bot_username,
                    escape=True,
                )
                if needed
                else template
            )
            if delivery.channel == "telegram":
                if len(rendered) > TELEGRAM_MESSAGE_MAX_LENGTH:
                    failed += 1
                    await self._mark_result(
                        int(delivery.delivery_id), success=False, error="message_too_long"
                    )
                    continue
                await self._queue_telegram(
                    delivery,
                    rendered,
                    buttons_for(language),
                    image=stored_image,
                )
                queued += 1
                continue

            subject_template = resolve_localized_text(
                subjects,
                language=language,
                default_language=self.settings.DEFAULT_LANGUAGE,
            )
            rendered_subject = (
                render_broadcast_text(
                    subject_template,
                    contexts.get(int(delivery.user_id)),
                    lang=language,
                    i18n=self.i18n,
                    settings=self.settings,
                    bot_username=self.bot_username,
                    escape=False,
                )
                if needed and subject_template
                else subject_template
            )
            email_recipients.append(
                BroadcastEmailRecipient(
                    user_id=int(delivery.user_id),
                    email=str(delivery.destination),
                    language_code=language,
                    message_text=rendered,
                    subject=rendered_subject or None,
                    buttons=email_links_for_buttons(buttons_for(language)),
                    delivery_id=int(delivery.delivery_id),
                )
            )

        for recipient in email_recipients:
            if recipient.delivery_id is not None:
                await self._mark_queued(recipient.delivery_id)
        email_queued = schedule_broadcast_emails(
            settings=self.settings,
            i18n=self.i18n,
            recipients=email_recipients,
            subject="",
            message_text="",
            session_factory=self.session_factory,
            actor_id=int(broadcast.created_by_admin_id) if broadcast.created_by_admin_id else None,
            target=str(broadcast.target),
            on_result=self._on_email_result,
            image=email_image,
        )
        async with self.session_factory() as session:
            await broadcast_dal.refresh_broadcast_stats(session, int(broadcast.broadcast_id))
        return BroadcastDispatchResult(queued, failed, email_queued, channels)

    async def _queue_telegram(
        self,
        delivery: AdminBroadcastDelivery,
        text: str,
        buttons: list[MessageButton],
        *,
        image: StoredMessageImage | None = None,
    ) -> None:
        if self.queue_manager is None:
            raise RuntimeError("queue_unavailable")
        delivery_id = int(delivery.delivery_id)

        parts = 1 if image is None or not text else 2
        remaining = parts
        failure: str | None = None
        telegram_status_recorded = False

        async def finish_part(error: Exception | None = None) -> None:
            nonlocal remaining, failure
            if error is not None and failure is None:
                failure = str(error)
            remaining -= 1
            if remaining == 0:
                await self._mark_result(
                    delivery_id,
                    success=failure is None,
                    error=failure,
                )

        async def on_success(_result: Any) -> None:
            await finish_part()

        async def on_failure(exc: Exception) -> None:
            nonlocal telegram_status_recorded
            if not telegram_status_recorded:
                telegram_status = await record_telegram_notification_failure(
                    self.session_factory,
                    int(delivery.user_id),
                    exc,
                )
                telegram_status_recorded = telegram_status is not None
            await finish_part(exc)

        chat_id = int(delivery.destination)
        markup = telegram_markup_for_buttons(buttons)
        if image is not None:
            photo_kwargs: dict[str, Any] = {
                "photo": FSInputFile(image.path),
                "callback": on_success,
                "error_callback": on_failure,
            }
            if not text:
                photo_kwargs["reply_markup"] = markup
            await self.queue_manager.send_photo(chat_id, **photo_kwargs)
        if text:
            await self.queue_manager.send_message(
                chat_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=markup,
                callback=on_success,
                error_callback=on_failure,
            )
        await self._mark_queued(delivery_id)

    async def _on_email_result(
        self,
        recipient: BroadcastEmailRecipient,
        success: bool,
        error: str | None,
    ) -> None:
        if recipient.delivery_id is not None:
            await self._mark_result(recipient.delivery_id, success=success, error=error)

    async def _mark_queued(self, delivery_id: int) -> None:
        async with self.session_factory() as session:
            await broadcast_dal.mark_delivery_queued(session, delivery_id)

    async def _mark_result(
        self,
        delivery_id: int,
        *,
        success: bool,
        error: str | None = None,
    ) -> None:
        async with self.session_factory() as session:
            await broadcast_dal.mark_delivery_result(
                session, delivery_id, success=success, error=error
            )

    async def _fail_broadcast(self, broadcast_id: int, error: str) -> None:
        async with self.session_factory() as session:
            await broadcast_dal.fail_broadcast(session, broadcast_id, error)
