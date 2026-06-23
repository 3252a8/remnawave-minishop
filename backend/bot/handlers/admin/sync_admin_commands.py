import logging
from typing import Optional, Union

from aiogram import Bot, types
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.webhook_queue import enqueue_webhook_event
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from config.settings import Settings
from db.dal import panel_sync_dal

from .sync_admin_common import (
    router,
)
from .sync_admin_runner import perform_sync


async def sync_command_handler(
    message_event: Union[types.Message, types.CallbackQuery],
    bot: Bot,
    settings: Settings,
    i18n_data: dict,
    panel_service: PanelApiService,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        logging.error("i18n missing in sync_command_handler")

        if isinstance(message_event, types.Message):
            await message_event.answer("Language error.")
        elif isinstance(message_event, types.CallbackQuery):
            await message_event.answer("Language error.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    target_chat_id = _sync_request_target_chat_id(message_event)
    if not target_chat_id:
        logging.error("Sync handler: could not determine target_chat_id.")
        if isinstance(message_event, types.CallbackQuery):
            await message_event.answer("Error initiating sync.", show_alert=True)
        return

    requested_by = getattr(getattr(message_event, "from_user", None), "id", None)
    queued = await _enqueue_manual_panel_sync(
        settings,
        requested_by=requested_by,
        target_chat_id=target_chat_id,
        language=current_lang,
    )
    if not queued:
        logging.warning("Admin (%s) failed to enqueue manual panel sync.", requested_by)
        await _answer_sync_request(message_event, _("sync_failed_simple"), show_alert=True)
        return

    await _answer_sync_request(
        message_event,
        _("admin_sync_initiated_from_panel")
        if isinstance(message_event, types.CallbackQuery)
        else _("sync_started_simple"),
    )
    logging.info("Admin (%s) queued panel sync from bot.", requested_by)


def _sync_request_target_chat_id(
    message_event: Union[types.Message, types.CallbackQuery],
) -> Optional[int]:
    chat = getattr(message_event, "chat", None)
    if chat and getattr(chat, "id", None) is not None:
        return int(chat.id)
    callback_message = getattr(message_event, "message", None)
    callback_chat = getattr(callback_message, "chat", None)
    if callback_chat and getattr(callback_chat, "id", None) is not None:
        return int(callback_chat.id)
    return None


async def _answer_sync_request(
    message_event: Union[types.Message, types.CallbackQuery],
    text: str,
    *,
    show_alert: bool = False,
) -> None:
    answer = getattr(message_event, "answer", None)
    if not callable(answer):
        return
    if isinstance(message_event, types.CallbackQuery):
        await answer(text, show_alert=show_alert)
        return
    await answer(text)


async def _enqueue_manual_panel_sync(
    settings: Settings,
    *,
    requested_by: Optional[int],
    target_chat_id: int,
    language: str,
) -> bool:
    payload = {
        "source": "bot_admin",
        "requested_by": requested_by,
        "target_chat_id": target_chat_id,
        "language": language,
    }
    return bool(await enqueue_webhook_event(settings, "panel_sync", payload, event_id=None))


@router.message(Command("syncstatus"))
async def sync_status_command_handler(
    message: types.Message, i18n_data: dict, settings: Settings, session: AsyncSession
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: Optional[JsonI18n] = i18n_data.get("i18n_instance")
    if not i18n:
        await message.answer("Language error.")
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    status_record_model = await panel_sync_dal.get_panel_sync_status(session)
    response_text = ""
    if status_record_model:
        last_time_val = status_record_model.last_sync_time
        last_time_str = last_time_val.strftime("%Y-%m-%d %H:%M:%S UTC") if last_time_val else "N/A"

        details_val = status_record_model.details
        details_str = details_val or "N/A"

        response_text = (
            f"<b>{_('admin_stats_last_sync_header')}</b>\n"
            f"  {_('admin_stats_sync_time')}: {last_time_str}\n"
            f"  {_('admin_stats_sync_status')}: {status_record_model.status}\n"
            f"  {_('admin_stats_sync_users_processed')}: {status_record_model.users_processed_from_panel}\n"  # noqa: E501
            f"  {_('admin_stats_sync_subs_synced')}: {status_record_model.subscriptions_synced}\n"
            f"  {_('admin_stats_sync_details_label')}: {details_str}"
        )
    else:
        response_text = _("admin_sync_status_never_run")

    await message.answer(response_text, parse_mode="HTML")


__all__ = [
    "_answer_sync_request",
    "_enqueue_manual_panel_sync",
    "_sync_request_target_chat_id",
    "enqueue_webhook_event",
    "perform_sync",
    "sync_command_handler",
    "sync_status_command_handler",
]
