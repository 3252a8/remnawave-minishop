"""Administrative controls for exchanging subscription days for add-ons."""

from bot.app.web.admin_settings_manifest_types import SettingField

SUBSCRIPTION_DAYS_SETTINGS_FIELDS: tuple[SettingField, ...] = (
    SettingField(
        "SUBSCRIPTION_DAYS_DEVICES_ENABLED",
        "bool",
        "payments",
        "Pay for extra devices with subscription days",
        "Allow paid period subscriptions to exchange remaining days for device packages.",
        subsection="subscription_days",
    ),
    SettingField(
        "SUBSCRIPTION_DAYS_TRAFFIC_ENABLED",
        "bool",
        "payments",
        "Pay for extra traffic with subscription days",
        "Allow paid period subscriptions to exchange days for regular or premium traffic.",
        subsection="subscription_days",
    ),
    SettingField(
        "SUBSCRIPTION_DAYS_MIN_REMAINING",
        "int",
        "payments",
        "Minimum remaining subscription days",
        "At least this many full days must remain after a purchase paid with days.",
        min=1,
        subsection="subscription_days",
    ),
)
