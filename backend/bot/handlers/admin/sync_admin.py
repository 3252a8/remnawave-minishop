import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union, cast

from aiogram import Bot, Router, types
from aiogram.filters import Command
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.infra.webhook_queue import enqueue_webhook_event
from bot.middlewares.i18n import JsonI18n
from bot.services.panel_api_service import PanelApiService
from bot.utils.text_sanitizer import panel_description_from_profile
from config.settings import Settings
from db.advisory_locks import acquire_subscription_background_sync_lock
from db.dal import panel_sync_dal, subscription_dal, user_dal
from db.models import Subscription, User

from .sync_admin_common import (
    _MISSING,
    _append_unique,
    _as_utc,
    _coerce_panel_telegram_id,
    _compact_log_value,
    _datetime_matches,
    _description_contains_email,
    _description_matches,
    _description_variants,
    _description_without_email,
    _format_counter,
    _format_panel_update_changes,
    _identity_panel_update_reasons,
    _log_sync_panel_patch,
    _normalize_description,
    _normalize_panel_email,
    _panel_description_for_user,
    _panel_expire_at,
    _panel_field_matches,
    _panel_identity_fields_update_payload,
    _panel_identity_matches_user,
    _panel_identity_needs_full_fetch,
    _panel_identity_needs_legacy_description_cleanup,
    _panel_identity_view_for_comparison,
    _panel_log_value,
    _panel_subscription_uuid,
    _panel_update_changes,
    _parse_panel_datetime,
    _repair_cp1251_mojibake,
    _safe_panel_telegram_id,
    _should_update_lifetime_used_traffic,
    _subscription_update_delta,
    _sync_lock,
    router,
)
from .sync_admin_identity import (
    _absorb_duplicate_panel_identity,
    _bind_panel_email_to_user,
    _extract_lifetime_used_traffic_bytes,
    _merge_local_duplicate_panel_user_if_needed,
    _panel_identity_payload_with_expiry,
    _prefetch_sync_indexes,
)
from .sync_admin_runner import (
    _perform_sync_impl,
    perform_sync,
)
from .sync_admin_commands import (
    _answer_sync_request,
    _enqueue_manual_panel_sync,
    _sync_request_target_chat_id,
    sync_command_handler,
    sync_status_command_handler,
)
