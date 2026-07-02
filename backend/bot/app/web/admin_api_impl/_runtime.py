"""HTTP API powering the admin section of the subscription Mini App.

All routes require an authenticated webapp session (cookie or Bearer
token) AND the resolved Telegram user id must appear in
``settings.ADMIN_IDS``. Authorization is enforced via the
``_require_admin_user_id`` helper, never trusted from the client.
"""

# ruff: noqa: F401, I001
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
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

from bot.app.web.route_contracts import (
    BINARY_RESPONSE_SCHEMA,
    BOOLEAN_SCHEMA,
    GENERIC_OK_RESPONSE,
    INTEGER_SCHEMA,
    JSON_ARRAY_SCHEMA,
    JSON_OBJECT_SCHEMA,
    NULLABLE_INTEGER_SCHEMA,
    NULLABLE_NUMBER_SCHEMA,
    NULLABLE_STRING_SCHEMA,
    NUMBER_SCHEMA,
    RouteContract,
    STRING_SCHEMA,
    loose_array_schema,
    loose_object_schema,
    ok_envelope_for,
    ok_envelope_with,
    register_contract,
    schema_ref,
)

from bot.app.web.request_parsing import parse_body, parse_body_or_400
from .schemas import (
    AdCreateBody,
    AdOut,
    AdToggleBody,
    AdminBackupRestoreBody,
    AdminAdsListOut,
    AdminBroadcastBody,
    AdminHealthOut,
    AdminLogsListOut,
    AdminMeOut,
    AdminPanelSyncOut,
    AdminPaymentsListOut,
    AdminSettingsPatchBody,
    AdminStatsOut,
    AdminSubscriptionOut,
    AdminTranslationsPatchBody,
    AdminUserBanBody,
    AdminUserOut,
    AdminUserTrialOut,
    AdminUserWithAvatarOut,
    AdminUserExtendBody,
    AdminUserHwidDeviceLimitBody,
    AdminUserMessageBody,
    AdminUserPremiumOverrideBody,
    AdminUserRegularTrafficOverrideBody,
    AdminUserTariffBody,
    AdminUserTrafficGrantBody,
    ImageUrlUploadBody,
    HttpBodyModel,
    HttpResponseModel,
    LogOut,
    PaymentDetailOut,
    PaymentOut,
    PromoCreateBody,
    PromoOut,
    PromoUpdateBody,
    TariffsSaveBody,
    ThemesSaveBody,
)

logger = logging.getLogger(__name__)


# ─── Auth ──────────────────────────────────────────────────────────

__all__: list[str] = []
