# ruff: noqa: F401,F403,F405,I001
import asyncio
import base64
import hashlib
import html
import hmac
import io
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from aiogram import Bot, Dispatcher
from aiohttp import ClientSession, ClientTimeout, web
from pydantic import BaseModel, ConfigDict, EmailStr, ValidationError, constr, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from bot.app.web.webapp_auth import (
    create_signed_telegram_oauth_state,
    create_telegram_oauth_nonce,
    create_webapp_session_token,
    validate_telegram_login_widget_data,
    validate_telegram_oauth_id_token,
    validate_telegram_webapp_init_data,
    verify_signed_telegram_oauth_state,
    verify_telegram_oauth_nonce,
    verify_webapp_session_token,
)
from bot.infra.redis import cache_delete, cache_get_json, cache_set_json, get_redis, redis_key
from bot.services.email_auth_service import EmailAuthService, is_disposable_email, normalize_email
from bot.services.email_templates import render_account_merged
from bot.services.promo_code_service import PromoCodeService
from bot.services.referral_service import ReferralService
from bot.services.subscription_service_impl.core import SubscriptionService
from bot.utils.config_link import prepare_config_links
from bot.utils.request_security import parse_ip_entries, request_client_ip
from bot.utils.text_sanitizer import (
    panel_description_from_profile,
    sanitize_display_name,
    sanitize_username,
)
from config.settings import Settings
from config.tariffs_config import (
    default_currency_key_for_settings,
    default_payment_currency_code_for_settings,
    payment_currency_code,
)
from db.dal import payment_dal, security_dal, subscription_dal, support_dal, user_dal
from db.dal.user_dal import UserMergeConflictError
from db.models import Payment, User, UserTelegramAvatar

logger = logging.getLogger(__name__)


def json_response(data: Any = None, **kwargs: Any) -> web.Response:
    return cast(web.Response, web.json_response(data, **kwargs))


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "templates" / "subscription_webapp.html"
ASSET_DIR = TEMPLATE_PATH.parent
APP_DEEPLINK_TEMPLATE_PATH = ASSET_DIR / "open_app_gateway.html"
APP_ROOT = Path(__file__).resolve().parents[5]
WEBAPP_LOGO_PROXY_PATH = "/webapp-logo"
WEBAPP_LOGO_CACHE_DIR = APP_ROOT / "data" / "webapp-logo"
WEBAPP_UPLOADED_LOGO_DIR = WEBAPP_LOGO_CACHE_DIR / "uploads"
WEBAPP_UPLOADED_LOGO_PATH = "/webapp-uploaded-logo"
WEBAPP_FAVICON_DIR = WEBAPP_LOGO_CACHE_DIR / "favicons"
WEBAPP_FAVICON_PATH = "/webapp-favicon"
WEBAPP_DEFAULT_BRAND_DIR = ASSET_DIR / "default-brand"
WEBAPP_DEFAULT_LOGO_FILE = WEBAPP_DEFAULT_BRAND_DIR / "default-logo.webp"
WEBAPP_DEFAULT_LOGO_PATH = "/webapp-default-logo.webp"
WEBAPP_DEFAULT_FAVICON_DIGEST = "19b2a242e5b7bc2d"
WEBAPP_DEFAULT_FAVICON_DIR = WEBAPP_DEFAULT_BRAND_DIR / "favicons" / WEBAPP_DEFAULT_FAVICON_DIGEST
WEBAPP_DEFAULT_FAVICON_URL = f"{WEBAPP_FAVICON_PATH}/{WEBAPP_DEFAULT_FAVICON_DIGEST}/icon-180.png"
WEBAPP_CONFIG_PLACEHOLDER = "<!-- WEBAPP_CONFIG_SCRIPT -->"
WEBAPP_I18N_PLACEHOLDER = "<!-- WEBAPP_I18N_SCRIPT -->"
WEBAPP_JS_PLACEHOLDER = "<!-- WEBAPP_JS_SCRIPT -->"
APP_REPOSITORY_URL = "https://minishop.minidoc.cc/"
DEV_MOCK_START_MARKER = "<!-- WEBAPP_DEV_MOCK_START -->"
DEV_MOCK_END_MARKER = "<!-- WEBAPP_DEV_MOCK_END -->"
WEBAPP_RATE_LIMIT_WINDOW_SECONDS = 60
WEBAPP_RATE_LIMIT_MAX_REQUESTS = 30
WEBAPP_LOGO_MAX_BYTES = 2 * 1024 * 1024
WEBAPP_THEME_CSS_MAX_BYTES = 512 * 1024
WEBAPP_THEME_ASSET_MAX_BYTES = 1024 * 1024
WEBAPP_THEME_ASSET_CONTENT_TYPES = {
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}
WEBAPP_TELEGRAM_AVATAR_MAX_BYTES = 128 * 1024
WEBAPP_TELEGRAM_AVATAR_REFRESH_SECONDS = 24 * 60 * 60
WEBAPP_TELEGRAM_AVATAR_FETCH_TIMEOUT_SECONDS = 4
WEBAPP_SESSION_COOKIE_NAME = "rw_webapp_session"
WEBAPP_CSRF_COOKIE_NAME = "rw_webapp_csrf"
WEBAPP_TELEGRAM_OAUTH_STATE_COOKIE_NAME = "rw_tg_oauth_state"
WEBAPP_CSRF_HEADER_NAME = "X-CSRF-Token"
WEBAPP_STATE_CHANGING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
ROBOTS_TX = """User-agent: *
Disallow: /

User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: OAI-SearchBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: ClaudeBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: PerplexityBot
Disallow: /

User-agent: Applebot-Extended
Disallow: /
"""
_APP_VERSION_CACHE: Optional[str] = None
WEBAPP_CSRF_EXEMPT_PATHS = {
    "/api/auth/telegram/nonce",
    "/api/auth/token",
    "/api/auth/email/request",
    "/api/auth/email/verify",
    "/api/auth/email/magic",
    "/api/auth/email/password",
    "/api/auth/logout",
}

_SHARED_HTTP_SESSION: Optional[ClientSession] = None
_SHARED_HTTP_SESSION_LOCK = asyncio.Lock()

__all__ = [name for name in globals() if not name.startswith("__")]
