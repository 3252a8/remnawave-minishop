"""Static core settings manifest fields for the admin web app."""

from __future__ import annotations

from bot.app.web.admin_settings_manifest_email_fields import EMAIL_SETTINGS_FIELDS
from bot.app.web.admin_settings_manifest_types import TRAFFIC_STRATEGY_CHOICES, SettingField
from bot.app.web.admin_settings_notification_manifest_fields import (
    NOTIFICATION_SETTINGS_FIELDS,
)
from bot.app.web.admin_settings_partner_manifest_fields import PARTNER_SETTINGS_FIELDS

SETTINGS_MANIFEST: list[SettingField] = [
    # ─── General ────────────────────────────────────────────────────
    SettingField(
        "WEBAPP_TITLE",
        "string",
        "general",
        "Web App title",
        placeholder="My subscription",
    ),
    SettingField(
        "DEFAULT_LANGUAGE",
        "string",
        "general",
        "Default Language",
        "Controls the 'Default Language' setting in admin overrides.",
    ),
    SettingField(
        "DEFAULT_CURRENCY_SYMBOL",
        "string",
        "general",
        "Default Currency Symbol",
        "Controls the 'Default Currency Symbol' setting in admin overrides.",
        placeholder="RUB",
    ),
    SettingField(
        "USER_TRAFFIC_STRATEGY",
        "string",
        "general",
        "Default Traffic Reset Strategy",
        choices=TRAFFIC_STRATEGY_CHOICES,
    ),
    SettingField(
        "SUPPORT_LINK",
        "url",
        "general",
        "Support Link",
        "Controls the 'Support Link' setting in admin overrides.",
    ),
    SettingField("SERVER_STATUS_URL", "url", "general", "Server Status URL"),
    SettingField("PRIVACY_POLICY_URL", "url", "general", "Privacy Policy URL"),
    SettingField("USER_AGREEMENT_URL", "url", "general", "User Agreement URL"),
    SettingField("DISABLE_WELCOME_MESSAGE", "bool", "general", "Disable Welcome Message"),
    SettingField(
        "START_COMMAND_DESCRIPTION",
        "string",
        "general",
        "Start Command Description",
        placeholder="",
    ),
    SettingField(
        "REGISTRATION_INVITE_ONLY_ENABLED",
        "bool",
        "general",
        "Invitation-only registration",
        (
            "When enabled, new users are created only through a valid referral invitation "
            "link. Existing users continue to sign in normally."
        ),
        optional=False,
    ),
    SettingField(
        "TELEGRAM_BOT_MENU_DISABLED",
        "bool",
        "general",
        "Disable bot menu",
        ("Hide the in-bot user interface and /tg command. Renewal prompts open the Mini App."),
    ),
    SettingField(
        "REQUIRED_CHANNEL_ID",
        "int",
        "general",
        "Required Channel ID",
        ("Controls the 'Required Channel ID' setting in admin overrides."),
    ),
    SettingField(
        "REQUIRED_CHANNEL_LINK",
        "string",
        "general",
        "Required Channel Link",
        ("Controls the 'Required Channel Link' setting in admin overrides."),
    ),
    # ─── Email auth & SMTP ─────────────────────────────────────────
    *EMAIL_SETTINGS_FIELDS,
    SettingField(
        "PANEL_API_URL",
        "url",
        "remnawave",
        "URL API Remnawave",
        "For example, https://panel.example.com/api.",
    ),
    SettingField(
        "PANEL_API_KEY",
        "string",
        "remnawave",
        "Remnawave API key",
        "Secret API key for the panel.",
        secret=True,
    ),
    SettingField(
        "PANEL_API_COOKIE",
        "string",
        "remnawave",
        "Cookie API Remnawave",
        "Optional Cookie header for Remnawave API requests behind a reverse proxy.",
        secret=True,
    ),
    SettingField(
        "PANEL_API_TOTAL_TIMEOUT_SECONDS",
        "float",
        "remnawave",
        "Panel API total timeout",
        "Maximum total time for one Remnawave API request, in seconds.",
        optional=False,
        min=1,
    ),
    SettingField(
        "PANEL_API_CONNECT_TIMEOUT_SECONDS",
        "float",
        "remnawave",
        "Panel API connect timeout",
        "Maximum time to get or open a Remnawave API connection, in seconds.",
        optional=False,
        min=1,
    ),
    SettingField(
        "PANEL_API_SOCK_CONNECT_TIMEOUT_SECONDS",
        "float",
        "remnawave",
        "Panel API socket connect timeout",
        "Maximum TCP/TLS connection time for Remnawave API, in seconds.",
        optional=False,
        min=1,
    ),
    SettingField(
        "PANEL_API_SOCK_READ_TIMEOUT_SECONDS",
        "float",
        "remnawave",
        "Panel API socket read timeout",
        "Maximum time to wait for response data from Remnawave API, in seconds.",
        optional=False,
        min=1,
    ),
    SettingField(
        "PANEL_WEBHOOK_SECRET",
        "string",
        "remnawave",
        "Remnawave webhook secret",
        (
            "Set the secret in Remnawave Panel and paste the same value here to verify "
            "incoming panel webhooks."
        ),
        secret=True,
        webhook_path="/webhook/panel",
        webhook_requires_base_url=True,
        webhook_provider_id="remnawave",
        webhook_hint_i18n_key="admin_settings_panel_webhook_url_hint",
        webhook_hint="Use this URL as WEBHOOK_URL in Remnawave Panel.",
    ),
    SettingField(
        "USER_SQUAD_UUIDS",
        "string",
        "remnawave",
        "Default Internal Squads",
        "Comma-separated UUIDs for the legacy mode without a JSON tariff catalog.",
    ),
    SettingField(
        "USER_EXTERNAL_SQUAD_UUID",
        "string",
        "remnawave",
        "Default External Squad",
        "Optional External Squad UUID for new users.",
    ),
    # ─── Web app appearance ────────────────────────────────────────
    SettingField(
        "SUBSCRIPTION_MINI_APP_URL",
        "url",
        "appearance",
        "Public Mini App URL",
        "For example, https://app.example.com/.",
    ),
    SettingField(
        "WEBAPP_PRIMARY_COLOR", "color", "appearance", "WebApp Primary Color", placeholder="#00fe7a"
    ),
    SettingField("WEBAPP_LOGO_URL", "url", "appearance", "WebApp Logo URL"),
    SettingField(
        "WEBAPP_FAVICON_USE_CUSTOM",
        "bool",
        "appearance",
        "Use separate favicon",
    ),
    SettingField("WEBAPP_FAVICON_URL", "url", "appearance", "Separate favicon URL"),
    SettingField("WEBAPP_LOGO_FAVICON_URL", "url", "appearance", "Favicon from logo"),
    SettingField("WEBAPP_ENABLED", "bool", "appearance", "WebApp Enabled"),
    SettingField(
        "SUBSCRIPTION_GUIDES_ENABLED",
        "bool",
        "subscription_guides",
        "Embedded install guides",
        "Open install instructions inside the Web App instead of an external connect page.",
    ),
    SettingField(
        "SUBSCRIPTION_GUIDES_BOT_MENU_ENABLED",
        "bool",
        "subscription_guides",
        "Open install guides from bot",
        (
            "Use the Telegram Mini App install screen for bot connect buttons and show "
            "public install guide links."
        ),
    ),
    SettingField(
        "SUBSCRIPTION_REISSUE_ENABLED",
        "bool",
        "subscription_guides",
        "Subscription link reissue",
        (
            "Let users reissue (revoke and regenerate) their subscription link from the "
            "Web App. The new link and connection instructions are delivered by email, "
            "so configured email auth is required."
        ),
    ),
    SettingField(
        "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED",
        "bool",
        "subscription_guides",
        "Use Remnawave Panel config",
        (
            "Fetch Subscription Page config from Remnawave Panel by the user's "
            "subscription short UUID."
        ),
    ),
    SettingField(
        "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED",
        "bool",
        "subscription_guides",
        "Enable admin JSON override",
        "Use the JSON field below instead of Remnawave Panel config. Disabled by default.",
    ),
    SettingField(
        "SUBSCRIPTION_PAGE_CONFIG_PATH",
        "string",
        "subscription_guides",
        "Subscription Page config path",
        "Fallback path to a Remnawave Subscription Page v1 JSON config file.",
        placeholder="data/subpage-config/multiapp.json",
    ),
    SettingField(
        "SUBSCRIPTION_PAGE_CONFIG_JSON",
        "json",
        "subscription_guides",
        "Subscription Page config JSON",
        (
            "Optional admin JSON override. It is applied only when the JSON override "
            "switch is enabled."
        ),
        placeholder='{\n  "version": "1"\n}',
    ),
    # ─── Subscription periods & pricing ────────────────────────────
    SettingField("MONTH_1_ENABLED", "bool", "pricing", "Month 1 Enabled"),
    SettingField("MONTH_3_ENABLED", "bool", "pricing", "Month 3 Enabled"),
    SettingField("MONTH_6_ENABLED", "bool", "pricing", "Month 6 Enabled"),
    SettingField("MONTH_12_ENABLED", "bool", "pricing", "Month 12 Enabled"),
    SettingField("RUB_PRICE_1_MONTH", "int", "pricing", "Rub Price 1 Month"),
    SettingField("RUB_PRICE_3_MONTHS", "int", "pricing", "Rub Price 3 Months"),
    SettingField("RUB_PRICE_6_MONTHS", "int", "pricing", "Rub Price 6 Months"),
    SettingField("RUB_PRICE_12_MONTHS", "int", "pricing", "Rub Price 12 Months"),
    SettingField("STARS_PRICE_1_MONTH", "int", "pricing", "Stars Price 1 Month"),
    SettingField("STARS_PRICE_3_MONTHS", "int", "pricing", "Stars Price 3 Months"),
    SettingField("STARS_PRICE_6_MONTHS", "int", "pricing", "Stars Price 6 Months"),
    SettingField("STARS_PRICE_12_MONTHS", "int", "pricing", "Stars Price 12 Months"),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_1_MONTH",
        "int",
        "pricing",
        "Referral Bonus Days Inviter 1 Month",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_3_MONTHS",
        "int",
        "pricing",
        "Referral Bonus Days Inviter 3 Months",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_6_MONTHS",
        "int",
        "pricing",
        "Referral Bonus Days Inviter 6 Months",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_12_MONTHS",
        "int",
        "pricing",
        "Referral Bonus Days Inviter 12 Months",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_1_MONTH",
        "int",
        "pricing",
        "Referral Bonus Days Referee 1 Month",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS",
        "int",
        "pricing",
        "Referral Bonus Days Referee 3 Months",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS",
        "int",
        "pricing",
        "Referral Bonus Days Referee 6 Months",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS",
        "int",
        "pricing",
        "Referral Bonus Days Referee 12 Months",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "TRAFFIC_PACKAGES",
        "string",
        "pricing",
        "Traffic Packages",
        "Controls the 'Traffic Packages' setting in admin overrides.",
    ),
    SettingField("STARS_TRAFFIC_PACKAGES", "string", "pricing", "Stars Traffic Packages"),
    SettingField(
        "SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED",
        "bool",
        "payments",
        "Show subscription description",
        "Shows this text before the user chooses a purchase or renewal period.",
        subsection="checkout",
    ),
    SettingField(
        "SUBSCRIPTION_PURCHASE_DESCRIPTION_RU",
        "text",
        "payments",
        "Subscription description (RU)",
        "Russian text shown during checkout. Leave empty to hide it for Russian users.",
        allow_empty=True,
        subsection="checkout",
    ),
    SettingField(
        "SUBSCRIPTION_PURCHASE_DESCRIPTION_EN",
        "text",
        "payments",
        "Subscription description (EN)",
        "English text shown during checkout. Leave empty to hide it for English users.",
        allow_empty=True,
        subsection="checkout",
    ),
    SettingField(
        "PAYMENT_REQUEST_TIMEOUT_SECONDS",
        "float",
        "payments",
        "Payment provider request timeout",
        "Maximum total time for one payment provider API request, in seconds.",
        optional=False,
        min=1,
        subsection="checkout",
    ),
    SettingField(
        "PAYMENT_FAILURE_NOTIFICATION_GRACE_SECONDS",
        "int",
        "payments",
        "Failed payment notification grace",
        (
            "Delay before notifying about a failed payment, allowing a successful retry "
            "to suppress stale errors. Set 0 to notify immediately."
        ),
        optional=False,
        min=0,
        subsection="checkout",
    ),
    # ─── Payment providers (toggles) ───────────────────────────────
    SettingField(
        "STARS_ENABLED",
        "bool",
        "payments",
        "Telegram Stars",
        subsection="Telegram Stars",
    ),
    SettingField(
        "STARS_ADMIN_ONLY_ENABLED",
        "bool",
        "payments",
        "Telegram Stars admin-only",
        (
            "Shows Telegram Stars only to users from ADMIN_IDS. "
            "Payment callbacks remain active for admin test payments."
        ),
        subsection="Telegram Stars",
        i18n_label_key="admin_settings_provider_admin_only_label",
        i18n_description_key="admin_settings_provider_admin_only_description",
    ),
    SettingField(
        "PAYMENT_METHODS_ORDER",
        "string",
        "payments",
        "Payment Methods Order",
        "Controls the 'Payment Methods Order' setting in admin overrides.",
        subsection="common",
    ),
    SettingField(
        "PAYMENT_METHODS_DISPLAY_MODE",
        "string",
        "payments",
        "Payment methods display",
        "Choose a compact dropdown or separate payment method buttons in checkout dialogs.",
        optional=False,
        choices=(("dropdown", "Dropdown"), ("buttons", "Separate buttons")),
        subsection="checkout",
        i18n_label_key="admin_settings_field_payment_methods_display_mode_label",
        i18n_description_key="admin_settings_field_payment_methods_display_mode_description",
    ),
    # ─── Trial ─────────────────────────────────────────────────────
    SettingField(
        "TRIAL_ENABLED",
        "bool",
        "pricing",
        "Trial Enabled",
        optional=False,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_DURATION_DAYS",
        "int",
        "pricing",
        "Trial Duration Days",
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_TRAFFIC_LIMIT_GB",
        "float",
        "pricing",
        "Trial Traffic Limit Gb",
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_PREMIUM_TRAFFIC_LIMIT_GB",
        "float",
        "pricing",
        "Trial premium traffic limit (GB)",
        (
            "Separate premium traffic limit for trial subscriptions. "
            "0 disables premium traffic enforcement."
        ),
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_HWID_DEVICE_LIMIT",
        "int",
        "pricing",
        "Trial HWID device limit",
        (
            "Hardware device limit for trial subscriptions. "
            "Empty keeps the panel/default limit; 0 means unlimited."
        ),
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_TRAFFIC_STRATEGY",
        "string",
        "pricing",
        "Trial Traffic Strategy",
        optional=False,
        choices=TRAFFIC_STRATEGY_CHOICES,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_WITHOUT_TELEGRAM_ENABLED",
        "bool",
        "pricing",
        "Trial Without Telegram",
        (
            "If disabled, email-only users must link Telegram before activating a trial. "
            "Disposable email domains always require Telegram."
        ),
        optional=False,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_SQUAD_UUIDS",
        "string",
        "pricing",
        "Trial Internal Squads",
        "Comma-separated UUIDs. Uses USER_SQUAD_UUIDS when empty.",
        subsection="trial",
    ),
    # ─── Referral program ──────────────────────────────────────────
    SettingField(
        "TRIAL_PREMIUM_SQUAD_UUIDS",
        "string",
        "pricing",
        "Premium Internal Squads for trial",
        (
            "Comma-separated premium internal squad UUIDs. "
            "Empty value disables premium squads for trials."
        ),
        subsection="trial",
    ),
    SettingField(
        "REFERRAL_PROGRAM_ENABLED",
        "bool",
        "pricing",
        "Referral program",
        (
            "Enable ordinary referral links, attribution, welcome bonuses and payment bonuses. "
            "Promo codes and the partner program remain available."
        ),
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_ONE_BONUS_PER_REFEREE",
        "bool",
        "pricing",
        "First-payment referral bonuses only",
        (
            "When enabled, later purchases by the same invited user do not grant referral "
            "bonuses to either side. The first successful payment still grants bonuses."
        ),
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_WELCOME_BONUS_DAYS",
        "int",
        "pricing",
        "Referral Welcome Bonus Days",
        min=0,
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
        "bool",
        "pricing",
        "Referral Welcome Bonus Without Telegram",
        (
            "If disabled, email-only users must link Telegram before receiving the referral "
            "welcome bonus. Disposable email domains always require Telegram."
        ),
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_WEBAPP_LINK_ENABLED",
        "bool",
        "pricing",
        "Website referral link",
        "Show the website referral link in the user Web App bonus section.",
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_TELEGRAM_LINK_ENABLED",
        "bool",
        "pricing",
        "Telegram referral link",
        "Show the Telegram bot referral link in the user Web App bonus section.",
        subsection="referral",
    ),
    *PARTNER_SETTINGS_FIELDS,
    SettingField(
        "LEGACY_REFS",
        "bool",
        "pricing",
        "Legacy ref links with user ID",
        (
            "Accept old links like /start ref_<telegram_id>, where the payload contains the "
            "inviter's Telegram/user ID."
        ),
        subsection="legacy_tariffs",
    ),
    SettingField(
        "DISPOSABLE_EMAIL_DOMAINS",
        "text",
        "pricing",
        "Disposable Email Domains",
        (
            "Comma-separated domains. Users without Telegram using these emails cannot "
            "claim trial or referral welcome bonus."
        ),
        placeholder="mailinator.com\ntemp-mail.org\nyopmail.com",
        subsection="referral",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED",
        "bool",
        "migrations",
        "Remnashop ref-code compatibility",
        (
            "Allows old Remnashop referral codes to resolve without changing their case or "
            "format. The importer enables it automatically."
        ),
        subsection="Remnashop",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED",
        "bool",
        "migrations",
        "Remnashop promo-code compatibility",
        (
            "Looks up promo codes in the original case first, then falls back to the current "
            "rules. Regular promo codes keep working as before."
        ),
        subsection="Remnashop",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_IMPORTED_AT",
        "string",
        "migrations",
        "Remnashop import date",
        "Operational marker for the latest Remnashop import, stored as an ISO timestamp.",
        subsection="Remnashop",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_NOTES",
        "text",
        "migrations",
        "Remnashop import notes",
        "Short importer summary: migrated entities and enabled compatibility modes.",
        subsection="Remnashop",
    ),
    # ─── Notifications, backups & support ──────────────────────────
    *NOTIFICATION_SETTINGS_FIELDS,
    # ─── Devices ───────────────────────────────────────────────────
    SettingField("MY_DEVICES_SECTION_ENABLED", "bool", "devices", "My Devices Section Enabled"),
    SettingField("USER_HWID_DEVICE_LIMIT", "int", "devices", "User HWID Device Limit", min=0),
    SettingField("USER_TRAFFIC_LIMIT_GB", "float", "devices", "User Traffic Limit Gb"),
    # ─── System ────────────────────────────────────────────────────
    SettingField(
        "TELEGRAM_DROP_NON_PRIVATE_UPDATES",
        "bool",
        "system",
        "Drop non-private Telegram updates",
        "Drops group/channel messages and callbacks before DB-backed middleware runs.",
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_ENABLED",
        "bool",
        "system",
        "Telegram anti-flood enabled",
        "Enables soft per-user limits for extreme Telegram update floods.",
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_WINDOW_SECONDS",
        "int",
        "system",
        "Anti-flood window",
        "Rolling window, in seconds, used by all Telegram anti-flood buckets.",
        min=1,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_MAX_UPDATES_PER_WINDOW",
        "int",
        "system",
        "All updates limit",
        "Maximum total Telegram updates from one actor during the window. 0 disables this bucket.",
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_MESSAGE_MAX_PER_WINDOW",
        "int",
        "system",
        "Messages limit",
        "Maximum message updates from one actor during the window. 0 disables this bucket.",
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_CALLBACK_MAX_PER_WINDOW",
        "int",
        "system",
        "Button callbacks limit",
        "Maximum callback-query updates from one actor during the window. 0 disables this bucket.",
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_INLINE_MAX_PER_WINDOW",
        "int",
        "system",
        "Inline queries limit",
        "Maximum inline-query updates from one actor during the window. 0 disables this bucket.",
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_START_MAX_PER_WINDOW",
        "int",
        "system",
        "/start limit",
        "Maximum /start messages from one actor during the window. 0 disables this bucket.",
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ANTIFLOOD_EXPENSIVE_CALLBACK_MAX_PER_WINDOW",
        "int",
        "system",
        "Expensive callbacks limit",
        (
            "Maximum payment, trial, promo and account-changing callbacks from one actor "
            "during the window. 0 disables this bucket."
        ),
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_ACTION_COOLDOWN_ENABLED",
        "bool",
        "system",
        "Action cooldowns enabled",
        "Deduplicates repeated payment and trial button presses from the same user.",
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_PAYMENT_CALLBACK_COOLDOWN_SECONDS",
        "int",
        "system",
        "Payment callback cooldown",
        (
            "Seconds to suppress an exact repeated payment callback from the same user. "
            "0 disables this cooldown."
        ),
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEGRAM_TRIAL_CALLBACK_COOLDOWN_SECONDS",
        "int",
        "system",
        "Trial callback cooldown",
        (
            "Seconds to suppress an exact repeated trial activation callback from the same user. "
            "0 disables this cooldown."
        ),
        min=0,
        subsection="telegram_antiflood",
    ),
    SettingField(
        "TELEMETRY_ENABLED",
        "bool",
        "system",
        "Anonymous install analytics",
        (
            "Sends one anonymous heartbeat per day (version, official/custom image marker, "
            "OS, locale, user-count range). No personal data, tokens or domains. Helps gauge "
            "active installs, versions in use and the share of modified builds. Toggling this "
            "off takes effect without a restart."
        ),
    ),
]
