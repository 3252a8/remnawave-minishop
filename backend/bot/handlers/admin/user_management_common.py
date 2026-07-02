import re
from collections.abc import Callable
from typing import Any

from aiogram import Bot, Router
from sqlalchemy.ext.asyncio import AsyncSession

from bot.utils.text_sanitizer import (
    sanitize_display_name,
    username_for_display,
)
from config.settings import Settings
from db.dal import user_dal
from db.models import User

router = Router(name="admin_user_management_router")
USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{5,32}$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


async def _resolve_bot_username(bot: Bot | None) -> str | None:
    """Best-effort resolution of the running bot's @username (cached by aiogram)."""
    if bot is None:
        return None
    try:
        me = await bot.me()
        return getattr(me, "username", None)
    except Exception:
        return None


def _format_traffic_period(strategy: str | None, get_text: Callable[..., str]) -> str | None:
    if not strategy:
        return None
    strategy_upper = str(strategy).upper()
    key_map = {
        "MONTH": "traffic_period_month",
        "WEEK": "traffic_period_week",
        "DAY": "traffic_period_day",
        "NO_RESET": "traffic_period_no_reset",
    }
    label_key = key_map.get(strategy_upper)
    return get_text(label_key) if label_key else strategy_upper


def _format_used_with_period(
    get_text: Callable[..., str], used_display: str, period_label: str | None
) -> str:
    if not period_label:
        return used_display
    return get_text(
        "traffic_used_with_period", traffic_used=used_display, traffic_period=period_label
    )


async def _find_user_by_admin_input(
    session: AsyncSession,
    input_text: str,
) -> User | None:
    if input_text.isdigit() or (input_text.startswith("-") and input_text[1:].isdigit()):
        try:
            return await user_dal.get_user_by_id(session, int(input_text))
        except ValueError:
            return None
    if EMAIL_REGEX.match(input_text):
        return await user_dal.get_user_by_email(session, input_text)
    if input_text.startswith("@") and USERNAME_REGEX.match(input_text[1:]):
        return await user_dal.get_user_by_username(session, input_text[1:])
    if USERNAME_REGEX.match(input_text):
        return await user_dal.get_user_by_username(session, input_text)
    return None


def _admin_user_reference_label(user: User | None, fallback_user_id: int | None = None) -> str:
    if user is None:
        return f"ID {fallback_user_id}" if fallback_user_id is not None else "N/A"

    first_name = sanitize_display_name(user.first_name) if user.first_name else ""
    last_name = sanitize_display_name(user.last_name) if user.last_name else ""
    full_name = f"{first_name} {last_name}".strip()
    if full_name:
        label = full_name
    elif user.username:
        label = username_for_display(user.username, with_at=True)
    elif user.email:
        label = user.email
    else:
        label = f"ID {user.user_id}"
    return f"{label} · ID {user.user_id}"


def _admin_user_button_label(user: User) -> str:
    label = _admin_user_reference_label(user)
    return label[:64]


def _enabled_admin_tariffs(settings: Settings) -> list:
    config = settings.tariffs_config
    if not config:
        return []
    return list(getattr(config, "enabled_tariffs", []) or [])


def _enabled_admin_period_tariffs(settings: Settings) -> list:
    return [
        tariff
        for tariff in _enabled_admin_tariffs(settings)
        if getattr(tariff, "billing_model", None) == "period"
    ]


def _resolve_admin_period_tariff_key(
    settings: Settings,
    explicit_tariff_key: str | None = None,
) -> tuple[str | None, str | None]:
    config = settings.tariffs_config
    if not config:
        return None, None

    explicit = str(explicit_tariff_key or "").strip()
    if explicit:
        try:
            tariff = config.require(explicit)
        except Exception:
            return None, "admin_user_tariff_invalid"
        if getattr(tariff, "billing_model", None) != "period":
            return None, "admin_user_tariff_invalid"
        return str(tariff.key), None

    enabled_tariffs = _enabled_admin_tariffs(settings)
    period_tariffs = _enabled_admin_period_tariffs(settings)
    if len(enabled_tariffs) == 1 and period_tariffs:
        return str(period_tariffs[0].key), None
    if not period_tariffs:
        return None, "admin_user_tariff_no_period_tariffs"
    return None, "admin_user_tariff_required"


def _admin_tariff_label(tariff: Any, lang: str) -> str:
    try:
        return str(tariff.name(lang))
    except Exception:
        return str(getattr(tariff, "key", "") or tariff)
