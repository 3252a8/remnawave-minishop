from __future__ import annotations

import secrets
from typing import Self

from pydantic import SecretStr, field_validator, model_validator

from config.support_links import normalize_support_link
from config.telegram_proxy import validate_telegram_bot_proxy_url
from config.traffic_strategy import normalize_traffic_limit_strategy


class SettingsValidationMixin:
    @field_validator("TELEGRAM_BOT_PROXY_URL")
    @classmethod
    def validate_telegram_bot_proxy_setting(cls, value: SecretStr | None) -> SecretStr | None:
        return validate_telegram_bot_proxy_url(value)

    @model_validator(mode="after")
    def validate_referral_link_visibility(self) -> Self:
        if not (
            bool(getattr(self, "REFERRAL_WEBAPP_LINK_ENABLED", False))
            or bool(getattr(self, "REFERRAL_TELEGRAM_LINK_ENABLED", False))
        ):
            raise ValueError("at least one referral link must remain enabled")
        return self

    @field_validator("SUPPORT_LINK", mode="before")
    @classmethod
    def normalize_support_link_setting(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        normalized = normalize_support_link(value)
        if normalized is None:
            raise ValueError(
                "SUPPORT_LINK must be an HTTP(S) URL, @username, or t.me/username link"
            )
        return normalized

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, value):
        if isinstance(value, str):
            value = value.strip().upper()
        if not value:
            return "INFO"
        return value

    @field_validator("POSTGRES_USER", "POSTGRES_PASSWORD", mode="before")
    @classmethod
    def validate_required_db_credentials(cls, value):
        if isinstance(value, str):
            value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("WEBAPP_SESSION_SECRET", "WEBHOOK_SECRET_TOKEN", mode="before")
    @classmethod
    def normalize_webapp_secrets(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
        if value:
            return value
        return secrets.token_urlsafe(32)

    @field_validator(
        "LOG_CHAT_ID",
        "LOG_THREAD_ID",
        "LOG_SUPPORT_THREAD_ID",
        "BACKUP_CHAT_ID",
        "BACKUP_THREAD_ID",
        "REQUIRED_CHANNEL_ID",
        mode="before",
    )
    @classmethod
    def validate_optional_int_fields(cls, value):
        """Convert empty strings to None for optional integer fields."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @field_validator(
        "REQUIRED_CHANNEL_LINK",
        "CRYPT4_REDIRECT_URL",
        "PRIVACY_POLICY_URL",
        "USER_AGREEMENT_URL",
        "SUBSCRIPTION_MINI_APP_URL",
        "WEBAPP_LOGO_URL",
        "TELEGRAM_OAUTH_CLIENT_SECRET",
        "TELEGRAM_OAUTH_REQUEST_ACCESS",
        "GOOGLE_OIDC_CLIENT_ID",
        "GOOGLE_OIDC_CLIENT_SECRET",
        "YANDEX_OIDC_CLIENT_ID",
        "YANDEX_OIDC_CLIENT_SECRET",
        "PASSKEY_RP_ID",
        "PASSKEY_RP_NAME",
        "PASSKEY_ORIGINS",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM_EMAIL",
        "SMTP_FROM_NAME",
        "SMTP_FALLBACK_PORTS",
        "BACKUP_COMPOSE_SOURCE_DIR",
        "BACKUP_COMPOSE_RESTORE_DIR",
        "PANEL_API_COOKIE",
        mode="before",
    )
    @classmethod
    def sanitize_optional_link(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("WEBAPP_API_BASE_URL", mode="before")
    @classmethod
    def normalize_webapp_api_base_url(cls, value):
        normalized = str(value or "/api").strip().rstrip("/")
        return normalized or "/api"

    @field_validator("MINISHOP_EDGE_TOKEN", mode="before")
    @classmethod
    def normalize_minishop_edge_token(cls, value):
        return str(value or "").strip()

    @field_validator("MINISHOP_EDGE_TOKEN_HEADER", mode="before")
    @classmethod
    def normalize_minishop_edge_token_header(cls, value):
        normalized = str(value or "").strip()
        return normalized or "X-Minishop-Edge-Token"

    @field_validator("USER_HWID_DEVICE_LIMIT", "TRIAL_HWID_DEVICE_LIMIT", mode="before")
    @classmethod
    def validate_optional_int(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("APP_RUNTIME_MODE", mode="before")
    @classmethod
    def normalize_app_runtime_mode(cls, value):
        normalized = str(value or "production").strip().lower().replace("-", "_")
        if not normalized:
            return "production"
        aliases = {
            "prod": "production",
            "dev": "development",
            "local_dev": "development",
            "testing": "test",
        }
        return aliases.get(normalized, normalized)

    @field_validator("PANEL_WRITE_MODE", mode="before")
    @classmethod
    def validate_panel_write_mode(cls, value):
        normalized = str(value or "auto").strip().lower().replace("-", "_")
        if normalized not in {"auto", "live", "dry_run"}:
            raise ValueError("PANEL_WRITE_MODE must be one of: auto, live, dry_run")
        return normalized

    @field_validator("USER_TRAFFIC_STRATEGY", "TRIAL_TRAFFIC_STRATEGY", mode="before")
    @classmethod
    def normalize_panel_traffic_strategy(cls, value):
        return normalize_traffic_limit_strategy(value)
