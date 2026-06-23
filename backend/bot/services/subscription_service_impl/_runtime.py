# ruff: noqa: F401,F403,F405,I001
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot.middlewares.i18n import JsonI18n
from bot.utils.config_link import prepare_config_links
from bot.utils.date_utils import add_months, month_start
from config.settings import Settings
from config.tariffs_config import (
    Tariff,
    TariffsConfig,
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
)
from db.dal import (
    payment_dal,
    promo_code_dal,
    subscription_dal,
    tariff_dal,
    user_billing_dal,
    user_dal,
)
from db.models import Subscription, User

from bot.services.email_auth_service import EmailAuthService
from bot.services.email_templates import render_payment_success
from bot.services.panel_api_service import PanelApiService
from bot.utils.text_sanitizer import panel_description_from_profile
from config.traffic_strategy import normalize_traffic_limit_strategy

if TYPE_CHECKING:
    from bot.payment_providers.shared import RecurringProviderService

    from ._typing import SubscriptionServiceMixinContract
else:
    RecurringProviderService = object
    SubscriptionServiceMixinContract = object

__all__ = [name for name in globals() if not name.startswith("__")]
