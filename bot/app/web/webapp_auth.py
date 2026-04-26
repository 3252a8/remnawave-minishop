import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl

from config.settings import Settings

logger = logging.getLogger(__name__)

# 5 minutes clock skew tolerance for Telegram clients
TELEGRAM_CLOCK_SKEW_SECONDS = 300


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64decode(raw: str) -> bytes:
    padded = raw + ("=" * (-len(raw) % 4))
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _session_secret(settings: Settings) -> bytes:
    return hmac.new(
        settings.WEBAPP_SESSION_SECRET.encode("utf-8"),
        b"remnawave-tg-shop-webapp-session",
        hashlib.sha256,
    ).digest()


def create_webapp_session_token(settings: Settings, user_id: int) -> str:
    now = int(time.time())
    payload = {
        "sub": int(user_id),
        "iat": now,
        "exp": now + max(60, int(settings.WEBAPP_SESSION_TTL_SECONDS)),
    }
    payload_part = _urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        _session_secret(settings),
        payload_part.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{payload_part}.{_urlsafe_b64encode(signature)}"


def verify_webapp_session_token(settings: Settings, token: str) -> Optional[int]:
    if not token or "." not in token:
        return None

    try:
        payload_part, signature_part = token.split(".", 1)
        expected_signature = hmac.new(
            _session_secret(settings),
            payload_part.encode("ascii"),
            hashlib.sha256,
        ).digest()
        received_signature = _urlsafe_b64decode(signature_part)
        if not hmac.compare_digest(expected_signature, received_signature):
            return None

        payload = json.loads(_urlsafe_b64decode(payload_part).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return int(payload["sub"])
    except Exception as exc:
        logger.debug("Failed to verify webapp session token: %s", exc)
        return None


def validate_telegram_webapp_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int,
) -> Optional[Dict[str, Any]]:
    """Validate Telegram Mini App initData and return the trusted user payload."""

    try:
        parsed_data = dict(parse_qsl(init_data or "", keep_blank_values=True))
        received_hash = parsed_data.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed_data.items())
        )
        secret_key = hmac.new(
            b"WebAppData",
            bot_token.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning("Telegram WebApp initData hash mismatch.")
            return None

        auth_date_raw = parsed_data.get("auth_date")
        if auth_date_raw:
            auth_date = int(auth_date_raw)
            now = int(time.time())
            max_age = max(60, int(max_age_seconds))
            if auth_date > now + TELEGRAM_CLOCK_SKEW_SECONDS or now - auth_date > max_age:
                logger.warning("Telegram WebApp initData auth_date is stale.")
                return None

        user_json = parsed_data.get("user")
        if not user_json:
            return None
        user_data = json.loads(user_json)
        if not user_data.get("id"):
            return None
        if parsed_data.get("start_param"):
            user_data["start_param"] = parsed_data.get("start_param")
        return user_data
    except Exception as exc:
        logger.warning("Failed to validate Telegram WebApp initData: %s", exc)
        return None


def validate_telegram_login_widget_data(
    auth_data: Any,
    bot_token: str,
    *,
    max_age_seconds: int,
) -> Optional[Dict[str, Any]]:
    """Validate Telegram Login Widget data and return the trusted user payload."""

    try:
        if isinstance(auth_data, str):
            parsed_data = dict(parse_qsl(auth_data or "", keep_blank_values=True))
        elif isinstance(auth_data, dict):
            parsed_data = {
                str(key): str(value)
                for key, value in auth_data.items()
                if value is not None
            }
        else:
            return None

        received_hash = str(parsed_data.pop("hash", "") or "")
        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={value}" for key, value in sorted(parsed_data.items())
        )
        secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning("Telegram Login Widget hash mismatch.")
            return None

        auth_date_raw = parsed_data.get("auth_date")
        if auth_date_raw:
            auth_date = int(auth_date_raw)
            now = int(time.time())
            max_age = max(60, int(max_age_seconds))
            if auth_date > now + TELEGRAM_CLOCK_SKEW_SECONDS or now - auth_date > max_age:
                logger.warning("Telegram Login Widget auth_date is stale.")
                return None

        user_id_raw = parsed_data.get("id")
        if not user_id_raw:
            return None
        int(user_id_raw)

        if not parsed_data.get("first_name"):
            return None

        return parsed_data
    except Exception as exc:
        logger.warning("Failed to validate Telegram Login Widget data: %s", exc)
        return None
