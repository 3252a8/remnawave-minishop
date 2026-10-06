"""Session, identity-provider and email authentication settings."""

import secrets

from pydantic import Field
from pydantic_settings import BaseSettings

from config.settings_defaults import DEFAULT_DISPOSABLE_EMAIL_DOMAINS


class AuthenticationSettings(BaseSettings):
    WEBAPP_SESSION_SECRET: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    EMAIL_AUTH_SECRET: str | None = Field(default=None)
    WEBHOOK_SECRET_TOKEN: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    WEBAPP_SESSION_TTL_SECONDS: int = Field(default=30 * 24 * 60 * 60)
    WEBAPP_AUTH_MAX_AGE_SECONDS: int = Field(default=24 * 60 * 60)
    WEBAPP_LOGIN_TOKEN_TTL_SECONDS: int = Field(default=10 * 60)
    TELEGRAM_LOGIN_ENABLED: bool = Field(default=True)
    TELEGRAM_LOGIN_RECOMMENDED: bool = Field(default=True)
    TELEGRAM_LOGIN_WIDE_BUTTON: bool = Field(default=False)
    EMAIL_LOGIN_ENABLED: bool = Field(default=True)
    EMAIL_LOGIN_RECOMMENDED: bool = Field(default=True)
    EMAIL_LOGIN_WIDE_BUTTON: bool = Field(default=True)
    EMAIL_ADDRESS_CHANGE_ENABLED: bool = Field(default=True)
    TELEGRAM_OAUTH_CLIENT_ID: int | None = Field(
        default=None,
        description="Telegram Web Login Client ID from BotFather. Defaults to the numeric bot ID from BOT_TOKEN.",  # noqa: E501
    )
    TELEGRAM_OAUTH_CLIENT_SECRET: str | None = Field(
        default=None,
        description="Telegram Web Login Client Secret from BotFather. Reserved for full OIDC authorization code integrations.",  # noqa: E501
    )
    TELEGRAM_OAUTH_REQUEST_ACCESS: str | None = Field(
        default="write",
        description="Comma-separated Telegram Login permissions to request: write,phone. Leave empty to request only OpenID profile.",  # noqa: E501
    )
    TELEGRAM_OAUTH_USE_BOT_PROXY: bool = Field(
        default=True,
        description=(
            "Reuse TELEGRAM_BOT_PROXY_URL for server-side Telegram OAuth token and JWKS requests "
            "when the proxy is configured"
        ),
    )
    GOOGLE_OIDC_ENABLED: bool = Field(default=False)
    GOOGLE_LOGIN_RECOMMENDED: bool = Field(default=True)
    GOOGLE_LOGIN_WIDE_BUTTON: bool = Field(default=False)
    GOOGLE_OIDC_CLIENT_ID: str | None = Field(default=None)
    GOOGLE_OIDC_CLIENT_SECRET: str | None = Field(default=None)
    YANDEX_OIDC_ENABLED: bool = Field(default=False)
    YANDEX_LOGIN_RECOMMENDED: bool = Field(default=True)
    YANDEX_LOGIN_WIDE_BUTTON: bool = Field(default=False)
    YANDEX_OIDC_CLIENT_ID: str | None = Field(default=None)
    YANDEX_OIDC_CLIENT_SECRET: str | None = Field(default=None)
    DISCORD_OIDC_ENABLED: bool = Field(default=False)
    DISCORD_LOGIN_RECOMMENDED: bool = Field(default=True)
    DISCORD_LOGIN_WIDE_BUTTON: bool = Field(default=False)
    DISCORD_OIDC_CLIENT_ID: str | None = Field(default=None)
    DISCORD_OIDC_CLIENT_SECRET: str | None = Field(default=None)
    PASSKEY_LOGIN_ENABLED: bool = Field(default=False)
    PASSKEY_LOGIN_RECOMMENDED: bool = Field(default=True)
    PASSKEY_LOGIN_WIDE_BUTTON: bool = Field(default=False)
    QR_LOGIN_ENABLED: bool = Field(default=False)
    QR_LOGIN_WIDE_BUTTON: bool = Field(default=False)
    PASSKEY_RP_ID: str | None = Field(
        default=None,
        description="WebAuthn relying-party domain. Empty means the public Web App hostname.",
    )
    PASSKEY_RP_NAME: str | None = Field(default=None)
    PASSKEY_ORIGINS: str | None = Field(
        default=None,
        description=(
            "Comma-separated allowed WebAuthn origins. Empty means the public Web App origin."
        ),
    )
    PASSKEY_CHALLENGE_TTL_SECONDS: int = Field(default=5 * 60)
    SMTP_HOST: str = Field(default="smtp-relay.brevo.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_FALLBACK_PORTS: str | None = Field(default="2525,465")
    SMTP_TIMEOUT_SECONDS: int = Field(default=30)
    SMTP_USERNAME: str | None = Field(default=None)
    SMTP_PASSWORD: str | None = Field(default=None)
    SMTP_FROM_EMAIL: str | None = Field(default=None)
    SMTP_FROM_NAME: str | None = Field(default=None)
    DISPOSABLE_EMAIL_DOMAINS: str = Field(
        default=DEFAULT_DISPOSABLE_EMAIL_DOMAINS,
        description=(
            "Disposable email domains treated as requiring Telegram for trial and "
            "referral welcome bonus abuse protection. Accepts commas or one domain per line."
        ),
    )
    SMTP_STARTTLS: bool = Field(default=True)
    SMTP_USE_SSL: bool = Field(default=False)
    EMAIL_CODE_TTL_SECONDS: int = Field(default=10 * 60)
    EMAIL_CODE_RESEND_SECONDS: int = Field(default=60)
    EMAIL_CODE_MAX_ATTEMPTS: int = Field(default=5)
    BRUTE_FORCE_MAX_FAILURES: int = Field(
        default=5,
        description="Maximum failed code attempts allowed within the throttle window before a temporary lockout is applied.",  # noqa: E501
    )
    BRUTE_FORCE_WINDOW_SECONDS: int = Field(
        default=15 * 60,
        description="Rolling window used to count failed email and promo code attempts.",
    )
    BRUTE_FORCE_LOCK_SECONDS: int = Field(
        default=30 * 60,
        description="Temporary lockout duration applied after too many failed code attempts.",
    )
