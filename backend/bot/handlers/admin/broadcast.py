import asyncio
import contextlib
import logging

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.inline.admin_keyboards import (
    get_admin_panel_keyboard,
    get_back_to_admin_panel_keyboard,
    get_broadcast_confirmation_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.services.broadcast_personalization import (
    BroadcastUserContext,
    known_shortcodes,
    telegram_html_error,
    unknown_shortcodes,
)
from bot.states.admin_states import AdminStates
from bot.utils import (
    MessageContent,
    get_message_content,
    send_message_by_type,
    send_message_via_queue,
)
from bot.utils.callback_answer import callback_data, callback_message
from bot.utils.message_queue import get_queue_manager
from config.settings import Settings
from db.dal import message_log_dal, user_dal

from .broadcast_shortcodes import (
    bot_username_for_shortcodes,
    load_admin_broadcast_contexts,
    localized_shortcode_error,
    message_content_html_text,
    render_personalized_admin_broadcast_text,
)

logger = logging.getLogger(__name__)

router = Router(name="admin_broadcast_router")
_BROADCAST_STATUS_TASKS: set[asyncio.Task[None]] = set()


async def broadcast_message_prompt_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        logger.error("i18n missing in broadcast_message_prompt_handler")
        await callback.answer("Language service error.", show_alert=True)
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    prompt_text = _("admin_broadcast_enter_message")

    if callback.message:
        try:
            await callback_message(callback).edit_text(
                prompt_text,
                reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            )
        except Exception as e:
            logger.warning("Could not edit message for broadcast prompt: %s. Sending new.", e)
            await callback_message(callback).answer(
                prompt_text,
                reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
            )
    await callback.answer()
    await state.set_state(AdminStates.waiting_for_broadcast_message)


@router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast_message_handler(
    message: types.Message,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
    session: AsyncSession,
    bot: Bot,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n:
        logger.error("i18n missing in process_broadcast_message_handler")
        await message.reply("Language service error.")
        return

    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    # Определяем тип содержимого и сохраняем данные в state
    entities = message.entities or message.caption_entities or []
    content = get_message_content(message)

    # Если нет ни текста, ни медиа — ошибка
    if not content.text and not content.file_id:
        await message.answer(_("admin_broadcast_error_no_message"))
        return

    unknown = sorted(unknown_shortcodes(content.text or ""))
    if unknown:
        await message.answer(
            localized_shortcode_error(
                i18n,
                current_lang,
                "admin_broadcast_unknown_shortcode",
                ", ".join(unknown),
            )
        )
        return

    needed_shortcodes = known_shortcodes(content.text or "")
    uses_shortcodes = bool(needed_shortcodes)
    broadcast_text = content.text
    preview_content = content
    preview_entities = entities
    if uses_shortcodes:
        broadcast_text = message_content_html_text(message, content).strip()
        html_error = telegram_html_error(broadcast_text)
        if html_error:
            await message.answer(
                localized_shortcode_error(
                    i18n,
                    current_lang,
                    "admin_broadcast_invalid_telegram_html",
                    html_error,
                )
            )
            return

        admin_user_id = int(message.from_user.id) if message.from_user else 0
        contexts = await load_admin_broadcast_contexts(
            session,
            settings,
            [admin_user_id] if admin_user_id else [],
            needed_shortcodes,
        )
        bot_username = await bot_username_for_shortcodes(bot, needed_shortcodes)
        preview_content = MessageContent(
            content.content_type,
            content.file_id,
            render_personalized_admin_broadcast_text(
                broadcast_text,
                contexts,
                admin_user_id,
                fallback_lang=current_lang,
                i18n=i18n,
                settings=settings,
                bot_username=bot_username,
            ),
        )
        preview_entities = []

    # Сохраняем данные для рассылки
    await state.update_data(
        broadcast_text=broadcast_text,
        broadcast_entities=preview_entities,
        broadcast_content_type=content.content_type,
        broadcast_file_id=content.file_id,
        broadcast_target="all",
        broadcast_uses_shortcodes=uses_shortcodes,
        broadcast_shortcodes=sorted(needed_shortcodes),
    )

    # Отправляем превью-копию того, что будет разослано
    try:
        # Для медиа-сообщений используем caption_entities, для текста - entities
        if content.content_type == "text":
            if uses_shortcodes:
                await send_message_by_type(
                    bot,
                    chat_id=message.chat.id,
                    content=preview_content,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                    disable_notification=True,
                )
            else:
                await send_message_by_type(
                    bot,
                    chat_id=message.chat.id,
                    content=preview_content,
                    parse_mode="HTML",
                    entities=preview_entities,
                    disable_web_page_preview=True,
                    disable_notification=True,
                )
        elif uses_shortcodes:
            await send_message_by_type(
                bot,
                chat_id=message.chat.id,
                content=preview_content,
                parse_mode="HTML",
                disable_web_page_preview=True,
                disable_notification=True,
            )
        else:
            await send_message_by_type(
                bot,
                chat_id=message.chat.id,
                content=preview_content,
                parse_mode="HTML",
                caption_entities=preview_entities,
                disable_web_page_preview=True,
                disable_notification=True,
            )
    except TelegramBadRequest as e:
        await message.answer(
            _(
                "admin_broadcast_invalid_html",
                error=str(e),
            )
        )
        return

    # Показываем короткое подтверждение без дублирования текста — сообщение выше служит превью
    confirmation_prompt = _("admin_broadcast_confirm_prompt_short")

    await message.answer(
        confirmation_prompt,
        reply_markup=get_broadcast_confirmation_keyboard(current_lang, i18n, target="all"),
    )
    await state.set_state(AdminStates.confirming_broadcast)


@router.callback_query(
    F.data.startswith("broadcast_target:"),
    AdminStates.confirming_broadcast,
)
async def change_broadcast_target_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    settings: Settings,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error updating selection.", show_alert=True)
        return

    new_target = callback_data(callback).split(":")[1]
    if new_target not in {"all", "active", "inactive", "expired"}:
        await callback.answer("Unknown target.", show_alert=True)
        return

    await state.update_data(broadcast_target=new_target)
    await state.get_data()
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)
    confirmation_prompt = _("admin_broadcast_confirm_prompt_short")
    with contextlib.suppress(Exception):
        await callback_message(callback).edit_text(
            confirmation_prompt,
            reply_markup=get_broadcast_confirmation_keyboard(current_lang, i18n, target=new_target),
        )
    await callback.answer()


@router.callback_query(F.data == "admin_action:main", AdminStates.waiting_for_broadcast_message)
async def cancel_broadcast_at_prompt_stage(
    callback: types.CallbackQuery,
    state: FSMContext,
    settings: Settings,
    i18n_data: dict,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error cancelling.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    try:
        await callback_message(callback).edit_text(
            _("admin_broadcast_cancelled_nav_back"), reply_markup=None
        )
    except Exception:
        await callback_message(callback).answer(_("admin_broadcast_cancelled_nav_back"))

    await callback.answer(_("admin_broadcast_cancelled_alert"))
    await state.clear()

    await callback_message(callback).answer(
        _(key="admin_panel_title"),
        reply_markup=get_admin_panel_keyboard(i18n, current_lang, settings),
    )


@router.callback_query(
    F.data.startswith("broadcast_final_action:"),
    AdminStates.confirming_broadcast,
)
async def confirm_broadcast_callback_handler(
    callback: types.CallbackQuery,
    state: FSMContext,
    i18n_data: dict,
    bot: Bot,
    settings: Settings,
    session: AsyncSession,
) -> None:
    current_lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    if not i18n or not callback.message:
        await callback.answer("Error processing broadcast confirmation.", show_alert=True)
        return
    _ = lambda key, **kwargs: i18n.gettext(current_lang, key, **kwargs)

    action = callback_data(callback).split(":")[1]
    user_fsm_data = await state.get_data()

    if action == "send":
        # Создаем объект контента из сохраненных данных
        content = MessageContent(
            content_type=user_fsm_data.get("broadcast_content_type", "text"),
            file_id=user_fsm_data.get("broadcast_file_id"),
            text=user_fsm_data.get("broadcast_text"),
        )
        entities = user_fsm_data.get("broadcast_entities", [])

        if not content.text and content.content_type == "text":
            await callback_message(callback).edit_text(_("admin_broadcast_error_no_message"))
            await state.clear()
            await callback.answer(_("admin_broadcast_error_no_message_alert"), show_alert=True)
            return

        await callback_message(callback).edit_text(
            _("admin_broadcast_sending_started"), reply_markup=None
        )
        await callback.answer()

        target = user_fsm_data.get("broadcast_target", "all")
        if target == "active":
            user_ids = await user_dal.get_user_ids_with_active_subscription(session)
        elif target == "inactive":
            user_ids = await user_dal.get_user_ids_without_active_subscription(session)
        elif target == "expired":
            user_ids = await user_dal.get_user_ids_with_expired_subscription(session)
        else:
            user_ids = await user_dal.get_all_active_user_ids_for_broadcast(session)

        sent_count = 0
        failed_count = 0
        admin_user = callback.from_user
        logger.info(
            "Admin %s broadcasting '%s...' to %s users.",
            admin_user.id,
            (content.text or "")[:50],
            len(user_ids),
        )

        # Get message queue manager
        queue_manager = get_queue_manager()
        if not queue_manager:
            await callback_message(callback).edit_text(
                "❌ Ошибка: система очередей не инициализирована", reply_markup=None
            )
            return

        needed_shortcodes = {
            str(code) for code in user_fsm_data.get("broadcast_shortcodes", []) if code
        }
        uses_shortcodes = bool(user_fsm_data.get("broadcast_uses_shortcodes")) and bool(
            content.text
        )
        contexts: dict[int, BroadcastUserContext] = {}
        bot_username = ""
        if uses_shortcodes:
            contexts = await load_admin_broadcast_contexts(
                session,
                settings,
                [int(uid) for uid in user_ids],
                needed_shortcodes,
            )
            bot_username = await bot_username_for_shortcodes(bot, needed_shortcodes)

        # Queue all messages for sending
        for uid in user_ids:
            try:
                message_content = content
                if uses_shortcodes:
                    message_content = MessageContent(
                        content.content_type,
                        content.file_id,
                        render_personalized_admin_broadcast_text(
                            content.text or "",
                            contexts,
                            int(uid),
                            fallback_lang=settings.DEFAULT_LANGUAGE,
                            i18n=i18n,
                            settings=settings,
                            bot_username=bot_username,
                        ),
                    )
                # Для медиа-сообщений используем caption_entities, для текста - entities
                if content.content_type == "text":
                    if uses_shortcodes:
                        await send_message_via_queue(
                            queue_manager,
                            uid,
                            message_content,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                        )
                    else:
                        await send_message_via_queue(
                            queue_manager,
                            uid,
                            message_content,
                            parse_mode="HTML",
                            entities=entities,
                            disable_web_page_preview=True,
                        )
                elif uses_shortcodes:
                    await send_message_via_queue(
                        queue_manager,
                        uid,
                        message_content,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                    )
                else:
                    await send_message_via_queue(
                        queue_manager,
                        uid,
                        message_content,
                        parse_mode="HTML",
                        caption_entities=entities,
                        disable_web_page_preview=True,
                    )
                sent_count += 1

                # Log successful queuing
                await message_log_dal.create_message_log(
                    session,
                    {
                        "user_id": admin_user.id,
                        "telegram_username": admin_user.username,
                        "telegram_first_name": admin_user.first_name,
                        "event_type": "admin_broadcast_queued",
                        "content": f"To user {uid}: [{content.content_type}] {(content.text or '')[:70]}...",  # noqa: E501
                        "is_admin_event": True,
                        "target_user_id": uid,
                    },
                )
            except Exception as e:
                failed_count += 1
                logger.warning("Failed to queue broadcast to %s: %s – %s", uid, type(e).__name__, e)
                await message_log_dal.create_message_log(
                    session,
                    {
                        "user_id": admin_user.id,
                        "telegram_username": admin_user.username,
                        "telegram_first_name": admin_user.first_name,
                        "event_type": "admin_broadcast_failed",
                        "content": f"For user {uid}: {type(e).__name__} – {str(e)[:70]}...",
                        "is_admin_event": True,
                        "target_user_id": uid,
                    },
                )

        try:
            await session.commit()
        except Exception as e_commit:
            await session.rollback()
            logger.error("Error committing broadcast logs: %s", e_commit)

        # Prepare queue stats presentation
        queue_stats = queue_manager.get_queue_stats()
        back_keyboard = get_back_to_admin_panel_keyboard(current_lang, i18n)
        initial_user_failed = queue_stats.get("user_failed_messages", 0)
        initial_group_failed = queue_stats.get("group_failed_messages", 0)

        def build_queue_status(stats: dict) -> str:
            dynamic_failed = max(
                0, stats.get("user_failed_messages", 0) - initial_user_failed
            ) + max(0, stats.get("group_failed_messages", 0) - initial_group_failed)
            total_failed = failed_count + dynamic_failed
            return str(
                _(
                    "broadcast_queue_result",
                    sent_count=sent_count,
                    failed_count=total_failed,
                    user_queue_size=stats["user_queue_size"],
                    group_queue_size=stats["group_queue_size"],
                )
            )

        result_message = build_queue_status(queue_stats)

        status_message = await callback_message(callback).answer(
            result_message,
            reply_markup=back_keyboard,
        )

        async def auto_update_queue_status() -> None:
            """Refresh queue stats message twice per second via message edit."""
            last_text = result_message
            # Update for up to 2 minutes (240 iterations at 0.5s intervals)
            max_iterations = 240
            for _ in range(max_iterations):
                await asyncio.sleep(0.5)

                stats = queue_manager.get_queue_stats()
                new_text = build_queue_status(stats)
                queues_drained = (
                    stats["user_queue_size"] == 0
                    and stats["group_queue_size"] == 0
                    and not stats.get("user_queue_processing")
                    and not stats.get("group_queue_processing")
                )

                if new_text != last_text:
                    try:
                        await status_message.edit_text(
                            new_text,
                            reply_markup=back_keyboard,
                        )
                        last_text = new_text
                    except TelegramBadRequest as e:
                        if "message is not modified" in str(e):
                            last_text = new_text
                        else:
                            logger.debug("Broadcast queue auto-update stopped: %s", e)
                            break
                    except Exception as e:
                        logger.debug("Broadcast queue auto-update unexpected error: %s", e)
                        break

                if queues_drained:
                    # Final refresh already attempted; exit loop.
                    break
            else:
                logger.debug("Broadcast queue auto-update reached time limit.")

        task = asyncio.create_task(auto_update_queue_status())
        _BROADCAST_STATUS_TASKS.add(task)
        task.add_done_callback(_BROADCAST_STATUS_TASKS.discard)

    elif action == "cancel":
        await callback_message(callback).edit_text(
            _("admin_broadcast_cancelled"),
            reply_markup=get_back_to_admin_panel_keyboard(current_lang, i18n),
        )
        await callback.answer()

    await state.clear()
