"""Persistent configuration shared by the admin API and delivery worker."""

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.promo_effects import PromoEffects, validate_effects
from config.settings import Settings
from db.dal import app_settings_dal

BIRTHDAY_CAMPAIGN_KEY = "BIRTHDAY_ACTIVATION_CAMPAIGN"
LEGACY_BIRTHDAY_DAYS_KEY = "BIRTHDAY_ACTIVATION_CODE_DAYS"


class BirthdayActivationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    enabled: bool = False
    valid_days: int = Field(default=7, ge=1, le=365)
    effects: PromoEffects = Field(default_factory=PromoEffects)

    def validate_for(self, settings: Settings) -> None:
        if self.enabled:
            validate_effects(
                self.effects,
                max_duration_multiplier=float(settings.PROMO_DURATION_MULTIPLIER_MAX),
                max_traffic_multiplier=float(settings.PROMO_TRAFFIC_MULTIPLIER_MAX),
            )


async def load_birthday_activation_config(
    session: AsyncSession, settings: Settings
) -> BirthdayActivationConfig:
    found, value = await app_settings_dal.get_override_value(session, BIRTHDAY_CAMPAIGN_KEY)
    if found:
        return BirthdayActivationConfig.model_validate(value)
    found, legacy_days = await app_settings_dal.get_override_value(
        session, LEGACY_BIRTHDAY_DAYS_KEY
    )
    days = legacy_days if found else settings.BIRTHDAY_ACTIVATION_CODE_DAYS
    days = max(0, min(365, int(days or 0)))
    return BirthdayActivationConfig(enabled=days > 0, effects=PromoEffects(bonus_days=days))
