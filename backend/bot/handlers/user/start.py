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

from .start_common import (
    _referral_code_lookup_candidates,
    _remnashop_referral_compat_enabled,
    _resolve_referrer_from_start_ref,
    router,
)
from .start_menus import (
    send_bot_interface_menu,
    send_main_menu,
    should_show_trial_button,
)
from .start_channel import ensure_required_channel_subscription
from .start_flow import start_command_handler
from .start_callbacks import (
    language_command_handler,
    main_action_callback_handler,
    select_language_callback_handler,
    tg_interface_command_handler,
    verify_channel_subscription_callback,
)
