"""Partner-program settings fields for the admin manifest."""

from bot.app.web.admin_settings_manifest_types import SettingField

PARTNER_SETTINGS_FIELDS: tuple[SettingField, ...] = (
    SettingField(
        "USER_BALANCE_ENABLED",
        "bool",
        "pricing",
        "User balance",
        "Show a personal balance and allow users to top it up and spend it.",
        subsection="balance",
    ),
    SettingField(
        "USER_BALANCE_CURRENCY",
        "string",
        "pricing",
        "User balance currency",
        "ISO-style currency code. Leave blank to follow the default payment currency.",
        subsection="balance",
    ),
    SettingField(
        "USER_BALANCE_TOPUP_MIN_AMOUNT",
        "float",
        "pricing",
        "Minimum balance top-up",
        min=0.01,
        subsection="balance",
    ),
    SettingField(
        "USER_BALANCE_TOPUP_MAX_AMOUNT",
        "float",
        "pricing",
        "Maximum balance top-up",
        min=0.01,
        subsection="balance",
    ),
    SettingField(
        "USER_BALANCE_TOPUP_PRESETS",
        "string",
        "pricing",
        "Balance top-up presets (JSON)",
        subsection="balance",
    ),
    SettingField(
        "PARTNER_PROGRAM_ENABLED",
        "bool",
        "pricing",
        "Partner program",
        "Enable applications, attribution, commissions and partner actions.",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_AUTO_ENROLLMENT_ENABLED",
        "bool",
        "pricing",
        "Automatic partner enrollment",
        (
            "Activate partner profiles for all current and future users without applications. "
            "Existing paused or closed profiles keep their status."
        ),
        subsection="partner",
    ),
    SettingField(
        "PARTNER_REFERRAL_PROGRAM_DISABLED",
        "bool",
        "pricing",
        "Disable referrals for partners",
        (
            "Hide referral actions for partner profiles and treat their existing referral "
            "links as partner attribution links."
        ),
        subsection="partner",
    ),
    SettingField(
        "PARTNER_WITHDRAWALS_ENABLED",
        "bool",
        "pricing",
        "Partner withdrawals",
        "Allow active partners to submit withdrawal requests.",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_BALANCE_PAYMENT_ENABLED",
        "bool",
        "pricing",
        "Partner balance payments",
        "Allow full or partial purchase payments from the partner balance.",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_CLIENT_WELCOME_BONUS_ENABLED",
        "bool",
        "pricing",
        "Partner client welcome bonus",
        (
            "Grant the referral welcome-bonus days once to a new user registered through an "
            "active partner link."
        ),
        subsection="partner",
    ),
    SettingField(
        "PARTNER_CLIENT_PAYMENT_BONUS_ENABLED",
        "bool",
        "pricing",
        "Partner client payment bonus",
        (
            "Grant the tariff referral-referee bonus days to partner clients after subscription "
            "payments."
        ),
        subsection="partner",
    ),
    SettingField(
        "PARTNER_ONE_BONUS_PER_CLIENT",
        "bool",
        "pricing",
        "First-payment partner client bonuses only",
        (
            "When enabled, later purchases by the same partner client do not grant tariff "
            "bonus days."
        ),
        subsection="partner",
    ),
    SettingField(
        "PARTNER_DEFAULT_COMMISSION_BPS",
        "int",
        "pricing",
        "Default partner commission (bps)",
        "Basis points: 3000 means 30%.",
        min=0,
        max=10000,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_COMMISSION_HOLD_DAYS",
        "int",
        "pricing",
        "Partner commission hold (days)",
        min=0,
        max=365,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_ELIGIBLE_CURRENCIES",
        "string",
        "pricing",
        "Partner eligible currencies (JSON)",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_EXCLUDED_SALE_MODES",
        "string",
        "pricing",
        "Partner excluded sale modes (JSON)",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_WITHDRAWAL_METHODS_JSON",
        "text",
        "pricing",
        "Partner withdrawal methods (JSON)",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_TELEGRAM_LINK_ENABLED",
        "bool",
        "pricing",
        "Telegram partner link",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_WEBAPP_LINK_ENABLED",
        "bool",
        "pricing",
        "Website partner link",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_APPLICATION_MESSAGE_MAX_LENGTH",
        "int",
        "pricing",
        "Partner application message limit",
        min=10,
        max=10000,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_MAX_ACTIVE_WITHDRAWALS",
        "int",
        "pricing",
        "Maximum active partner withdrawals",
        min=1,
        max=50,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_REAPPLICATION_ENABLED",
        "bool",
        "pricing",
        "Partner reapplication",
        subsection="partner",
    ),
    SettingField(
        "PARTNER_REAPPLICATION_COOLDOWN_DAYS",
        "int",
        "pricing",
        "Partner reapplication cooldown (days)",
        min=0,
        max=3650,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_LIST_PAGE_LIMIT",
        "int",
        "pricing",
        "Partner list page limit",
        min=10,
        max=200,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_APPLICATION_RATE_LIMIT_HOURS",
        "int",
        "pricing",
        "Partner application rate limit (hours)",
        min=1,
        max=8760,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_WITHDRAWAL_RATE_LIMIT_SECONDS",
        "int",
        "pricing",
        "Partner withdrawal rate limit (seconds)",
        min=1,
        max=3600,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_AUDIT_RETENTION_DAYS",
        "int",
        "pricing",
        "Partner audit retention (days)",
        min=30,
        max=3650,
        subsection="partner",
    ),
    SettingField(
        "PARTNER_REQUISITES_RETENTION_DAYS",
        "int",
        "pricing",
        "Partner requisites retention (days)",
        min=1,
        max=3650,
        subsection="partner",
    ),
)

__all__ = ["PARTNER_SETTINGS_FIELDS"]
