import logging
import re
from datetime import datetime, timezone
from typing import Optional, Union

from aiogram import Bot, F, Router, types
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.utils.text_decorations import html_decoration as hd
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra import events
from bot.infra.event_payloads import ReferralBonusGrantedPayload
from bot.keyboards.inline.user_keyboards import (
    get_bot_interface_inline_keyboard,
    get_channel_subscription_keyboard,
    get_information_links_keyboard,
    get_language_selection_keyboard,
    get_main_menu_inline_keyboard,
    telegram_bot_menu_enabled_for_user,
)
from bot.middlewares.i18n import JsonI18n, normalize_locale_language_code
from bot.services.panel_api_service import PanelApiService
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service import SubscriptionService
from bot.services.telegram_notifications import TELEGRAM_NOTIFICATIONS_ENABLED
from bot.utils.callback_answer import (
    callback_data,
    callback_message,
    message_bot,
    message_from_user,
    safe_answer_callback,
)
from bot.utils.channel_subscription import (
    is_required_channel_access_error,
    normalize_required_channel_id,
    resolve_required_channel_link,
)
from bot.utils.install_links import (
    append_install_share_link_text,
    ensure_user_install_guide_links,
)
from bot.utils.text_sanitizer import sanitize_display_name, sanitize_username
from config.settings import Settings
from db.dal import user_dal
from db.models import User

router = Router(name="user_start_router")


def _remnashop_referral_compat_enabled(settings: Settings) -> bool:
    return bool(getattr(settings, "MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED", False))


def _referral_code_lookup_candidates(
    raw_ref_value: str,
    *,
    remnashop_compat: bool,
) -> list[str]:
    value = str(raw_ref_value or "").strip()
    if not value:
        return []

    candidates = [value]
    if value and value[0].lower() == "u":
        stripped_current_prefix = value[1:]
        if remnashop_compat:
            candidates.append(stripped_current_prefix)
        else:
            candidates = [stripped_current_prefix]

    unique: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate and candidate not in unique:
            unique.append(candidate)
    return unique


async def _resolve_referrer_from_start_ref(
    session: AsyncSession,
    raw_ref_value: str,
    *,
    settings: Settings,
    current_user_id: int,
) -> Optional[int]:
    ref_user: Optional[User] = None
    if raw_ref_value.isdigit() and settings.LEGACY_REFS:
        potential_referrer_id = int(raw_ref_value)
        if potential_referrer_id != current_user_id:
            ref_user = await user_dal.get_user_by_id(session, potential_referrer_id)

    include_legacy = _remnashop_referral_compat_enabled(settings)
    if not ref_user:
        for code in _referral_code_lookup_candidates(
            raw_ref_value,
            remnashop_compat=include_legacy,
        ):
            ref_user = await user_dal.get_user_by_referral_code(
                session,
                code,
                include_legacy=include_legacy,
            )
            if ref_user:
                break

    if ref_user and ref_user.user_id != current_user_id:
        return int(ref_user.user_id)
    return None
