import hashlib
from typing import Any, Optional, Protocol, cast

from aiogram import Router, types
from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.inline.user_keyboards import (
    get_tariff_packages_keyboard,
    get_tariff_periods_keyboard,
)
from bot.middlewares.i18n import JsonI18n
from bot.payment_providers import provider_supports_recurring
from bot.payment_providers.shared import service_supports_recurring
from bot.services.subscription_service import SubscriptionService
from bot.utils.callback_answer import (
    message_from_user,
)
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.models import Subscription

router = Router(name="user_subscription_core_router")


class _TrafficPackages(Protocol):
    def for_currency(self, currency: str) -> Any: ...


class _PurchaseTariff(Protocol):
    billing_model: str
    traffic_packages: _TrafficPackages

    def name(self, lang: str) -> str: ...
    def description(self, lang: str) -> str: ...


def _shorten_hwid_for_display(hwid: Optional[str], max_length: int = 24) -> str:
    """Trim HWID for button text to keep within Telegram limits."""
    if not hwid:
        return "-"
    hwid_str = str(hwid)
    if len(hwid_str) <= max_length:
        return hwid_str
    return f"{hwid_str[:8]}...{hwid_str[-6:]}"


def _hwid_callback_token(hwid: Optional[str]) -> str:
    """Stable short token for callback_data; avoids 64b limit with raw HWID."""
    hwid_str = str(hwid or "")
    return hashlib.sha256(hwid_str.encode()).hexdigest()[:32]


def _enabled_tariffs(settings: Settings) -> list:
    config = settings.tariffs_config
    return list(config.enabled_tariffs) if config else []


def _has_multiple_enabled_tariffs(settings: Settings) -> bool:
    return len(_enabled_tariffs(settings)) > 1


def _recurring_service_for_subscription(
    subscription_service: SubscriptionService,
    sub: Optional[Subscription],
) -> object:
    provider = str(getattr(sub, "provider", "") or "").strip().lower()
    if not provider:
        return None
    resolver = getattr(subscription_service, "recurring_service_for", None)
    if callable(resolver):
        return resolver(provider)
    services = getattr(subscription_service, "recurring_provider_services", {}) or {}
    return services.get(provider)


def _auto_renew_control_visible(
    subscription_service: SubscriptionService,
    sub: Optional[Subscription],
) -> bool:
    if not sub or not provider_supports_recurring(getattr(sub, "provider", None)):
        return False
    service = _recurring_service_for_subscription(subscription_service, sub)
    return bool(getattr(sub, "auto_renew_enabled", False) or service_supports_recurring(service))


def _tariff_purchase_markup(
    tariff: _PurchaseTariff,
    current_lang: str,
    i18n: JsonI18n,
    settings: Settings,
    back_callback: str = "main_action:subscribe",
    callback_context: Optional[str] = None,
) -> InlineKeyboardMarkup:
    if tariff.billing_model == "period":
        return cast(
            InlineKeyboardMarkup,
            get_tariff_periods_keyboard(
                tariff,
                current_lang,
                i18n,
                settings,
                back_callback=back_callback,
                callback_context=callback_context,
            ),
        )
    default_currency = default_currency_key_for_settings(settings)
    return cast(
        InlineKeyboardMarkup,
        get_tariff_packages_keyboard(
            tariff,
            tariff.traffic_packages.for_currency(default_currency),
            current_lang,
            i18n,
            currency_symbol=default_payment_currency_code_for_settings(settings),
            back_callback=back_callback,
            callback_context=callback_context,
        ),
    )


def _tariff_purchase_text(
    tariff: _PurchaseTariff, current_lang: str, i18n: JsonI18n, settings: Settings
) -> str:
    if not _has_multiple_enabled_tariffs(settings):
        if tariff.billing_model == "period":
            return str(i18n.gettext(current_lang, "select_subscription_period"))
        return str(i18n.gettext(current_lang, "select_traffic_package"))
    return f"{tariff.name(current_lang)}\n{tariff.description(current_lang)}".strip()


def _with_subscription_purchase_description(
    text: str,
    settings: Settings,
    current_lang: str,
    *,
    include: bool,
) -> str:
    if not include:
        return text
    description_resolver = settings.subscription_purchase_description
    description = description_resolver(current_lang) if callable(description_resolver) else ""
    if not description:
        return text
    return f"{description}\n\n{text}"


def _format_premium_bytes(value: object) -> str:
    try:
        bytes_value = max(0, int(str(value or 0)))
    except (TypeError, ValueError):
        bytes_value = 0
    return f"{bytes_value / 2**30:.2f} GB"


def _event_user_id(event: types.Message | types.CallbackQuery) -> int:
    if isinstance(event, types.CallbackQuery):
        return int(event.from_user.id)
    return int(message_from_user(event).id)


def _format_premium_usage_limit(active: dict[str, object]) -> str:
    used = _format_premium_bytes(active.get("premium_used_bytes"))
    limit = _format_premium_bytes(active.get("premium_limit_bytes"))
    return f"{used} из {limit}"
