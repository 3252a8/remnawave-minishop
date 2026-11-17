from aiogram.types import CallbackQuery

from bot.middlewares.i18n import JsonI18n
from config.settings import Settings


async def accept_promo_validity_callback(
    callback: CallbackQuery, draft: dict[str, object], i18n_data: dict, settings: Settings
) -> bool:
    message_id = draft.get("promo_validity_message_id")
    if callback.message and (message_id is None or message_id == callback.message.message_id):
        return True
    i18n: JsonI18n | None = i18n_data.get("i18n_instance")
    lang = i18n_data.get("current_language", settings.DEFAULT_LANGUAGE)
    await callback.answer(
        i18n.gettext(lang, "error_try_again") if i18n else "Error", show_alert=True
    )
    return False
