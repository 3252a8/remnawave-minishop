"""Trial-related runtime settings."""

from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class TrialSettings(BaseSettings):
    TRIAL_ENABLED: bool = Field(default=True)
    TRIAL_PAYMENT_ENABLED: bool = Field(
        default=False,
        description="Require a successful payment before trial activation.",
    )
    TRIAL_PAYMENT_PRICE: float = Field(
        default=100.0,
        ge=0,
        allow_inf_nan=False,
        description="Trial activation price in the default payment currency.",
    )
    TRIAL_PAYMENT_STARS_PRICE: int = Field(
        default=100,
        ge=0,
        description="Trial activation price in Telegram Stars; 0 disables Stars for trial.",
    )
    TRIAL_DURATION_DAYS: int = Field(default=3)
    TRIAL_TRAFFIC_LIMIT_GB: float | None = Field(default=5.0)
    TRIAL_PREMIUM_TRAFFIC_LIMIT_GB: float | None = Field(
        default=0.0,
        description=(
            "Separate premium traffic limit for trial subscriptions. "
            "0 disables premium traffic enforcement for trials."
        ),
    )
    TRIAL_HWID_DEVICE_LIMIT: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Hardware device limit for trial subscriptions. "
            "Empty keeps the panel/default limit; 0 means unlimited."
        ),
    )
    TRIAL_DAYS_STRATEGY: Literal["add_remaining", "start_from_payment"] = Field(
        default="add_remaining",
        description=(
            "How a paid tariff starts while a trial is active: keep the remaining trial "
            "days or start the paid period on the payment date."
        ),
    )
    TRIAL_TRAFFIC_STRATEGY: str = Field(default="NO_RESET")
    TRIAL_WITHOUT_OAUTH_ENABLED: bool = Field(
        default=True,
        description=(
            "Allow trial activation without a linked Telegram or external OAuth identity. "
            "Disposable email domains are still blocked until Telegram is linked."
        ),
        validation_alias=AliasChoices(
            "TRIAL_WITHOUT_OAUTH_ENABLED",
            "TRIAL_WITHOUT_TELEGRAM_ENABLED",
        ),
    )
    TRIAL_SQUAD_UUIDS: str | None = Field(
        default=None,
        description=(
            "Comma-separated UUIDs of internal squads to assign during trial activation. "
            "Falls back to USER_SQUAD_UUIDS when empty."
        ),
    )
    TRIAL_PREMIUM_SQUAD_UUIDS: str | None = Field(
        default=None,
        description=(
            "Comma-separated premium internal squad UUIDs to assign during trial activation. "
            "Empty value disables premium squads for trials."
        ),
    )
