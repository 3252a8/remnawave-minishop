# ruff: noqa: F401,F403,F405,I001
"""HTTP API powering the admin section of the subscription Mini App.

All routes require an authenticated webapp session (cookie or Bearer
token) AND the resolved Telegram user id must appear in
``settings.ADMIN_IDS``. Authorization is enforced via the
``_require_admin_user_id`` helper, never trusted from the client.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from aiohttp import web
from pydantic import ValidationError
from sqlalchemy import Float, and_, case, cast, or_, select
from sqlalchemy import func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.admin_settings_manifest import (
    manifest_payload,
)
from bot.infra.webhook_queue import enqueue_webhook_event
from bot.services.referral_service import ReferralService
from bot.services.settings_override_service import (
    current_value,
    update_overrides,
)
from bot.utils import MessageContent, send_message_via_queue
from bot.utils.message_queue import get_queue_manager
from config.settings import Settings
from config.tariffs_config import TariffsConfig, default_payment_currency_code_for_settings
from db.dal import (
    ad_dal,
    app_settings_dal,
    locale_overrides_dal,
    message_log_dal,
    panel_sync_dal,
    payment_dal,
    promo_code_dal,
    subscription_dal,
    user_dal,
)
from db.models import (
    AdCampaign,
    MessageLog,
    Payment,
    PromoCode,
    Subscription,
    User,
    UserTelegramAvatar,
)

logger = logging.getLogger(__name__)


# ─── Auth ──────────────────────────────────────────────────────────

__all__ = [name for name in globals() if not name.startswith("__")]
