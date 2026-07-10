"""Static core settings manifest fields for the admin web app."""

from __future__ import annotations

from bot.app.web.admin_settings_manifest_email_fields import EMAIL_SETTINGS_FIELDS
from bot.app.web.admin_settings_manifest_types import TRAFFIC_STRATEGY_CHOICES, SettingField

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
        "Язык по умолчанию",
        "Используется для приветственных сообщений и публичных страниц.",
    ),
    SettingField(
        "DEFAULT_CURRENCY_SYMBOL",
        "string",
        "general",
        "Валюта",
        "Например, RUB, USD, EUR.",
        placeholder="RUB",
    ),
    SettingField(
        "SUPPORT_LINK", "url", "general", "Ссылка поддержки", "Куда вести пользователей за помощью."
    ),
    SettingField("SERVER_STATUS_URL", "url", "general", "Ссылка на статус серверов"),
    SettingField("PRIVACY_POLICY_URL", "url", "general", "Политика конфиденциальности"),
    SettingField("USER_AGREEMENT_URL", "url", "general", "Пользовательское соглашение"),
    SettingField("DISABLE_WELCOME_MESSAGE", "bool", "general", "Скрыть приветствие /start"),
    SettingField(
        "START_COMMAND_DESCRIPTION", "string", "general", "Описание /start", placeholder=""
    ),
    SettingField(
        "REGISTRATION_INVITE_ONLY_ENABLED",
        "bool",
        "general",
        "Регистрация только по приглашению",
        (
            "Если включено, новые пользователи создаются только по валидной "
            "реферальной ссылке. Существующие пользователи продолжают входить как обычно."
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
        "ID обязательного канала",
        (
            "Telegram ID канала для проверки подписки. Если бот видит канал, "
            "ссылка кнопки будет получена автоматически."
        ),
    ),
    SettingField(
        "REQUIRED_CHANNEL_LINK",
        "string",
        "general",
        "Ссылка на канал",
        (
            "Необязательно: публичный @username или invite-link, "
            "если ссылку нельзя получить по ID канала."
        ),
    ),
    # ─── Email auth & SMTP ─────────────────────────────────────────
    *EMAIL_SETTINGS_FIELDS,
    SettingField(
        "PANEL_API_URL",
        "url",
        "remnawave",
        "URL API Remnawave",
        "Например, https://panel.example.com/api.",
    ),
    SettingField(
        "PANEL_API_KEY",
        "string",
        "remnawave",
        "API-ключ Remnawave",
        "Секретный ключ API панели.",
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
        "Секрет вебхуков Remnawave",
        "Используется для проверки входящих вебхуков панели.",
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
        "Internal Squads по умолчанию",
        "UUID через запятую для legacy-режима без JSON-каталога тарифов.",
    ),
    SettingField(
        "USER_EXTERNAL_SQUAD_UUID",
        "string",
        "remnawave",
        "External Squad по умолчанию",
        "Необязательный UUID External Squad для новых пользователей.",
    ),
    # ─── Web app appearance ────────────────────────────────────────
    SettingField(
        "SUBSCRIPTION_MINI_APP_URL",
        "url",
        "appearance",
        "Публичный URL Mini App",
        "Например, https://app.example.com/.",
    ),
    SettingField(
        "WEBAPP_PRIMARY_COLOR", "color", "appearance", "Основной цвет", placeholder="#00fe7a"
    ),
    SettingField("WEBAPP_LOGO_URL", "url", "appearance", "URL логотипа"),
    SettingField(
        "WEBAPP_FAVICON_USE_CUSTOM",
        "bool",
        "appearance",
        "Использовать отдельную favicon",
    ),
    SettingField("WEBAPP_FAVICON_URL", "url", "appearance", "URL отдельной favicon"),
    SettingField("WEBAPP_LOGO_FAVICON_URL", "url", "appearance", "Favicon из логотипа"),
    SettingField("WEBAPP_ENABLED", "bool", "appearance", "Web App включён"),
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
    SettingField("MONTH_1_ENABLED", "bool", "pricing", "Тариф 1 месяц"),
    SettingField("MONTH_3_ENABLED", "bool", "pricing", "Тариф 3 месяца"),
    SettingField("MONTH_6_ENABLED", "bool", "pricing", "Тариф 6 месяцев"),
    SettingField("MONTH_12_ENABLED", "bool", "pricing", "Тариф 12 месяцев"),
    SettingField("RUB_PRICE_1_MONTH", "int", "pricing", "Цена 1 мес. (RUB)"),
    SettingField("RUB_PRICE_3_MONTHS", "int", "pricing", "Цена 3 мес. (RUB)"),
    SettingField("RUB_PRICE_6_MONTHS", "int", "pricing", "Цена 6 мес. (RUB)"),
    SettingField("RUB_PRICE_12_MONTHS", "int", "pricing", "Цена 12 мес. (RUB)"),
    SettingField("STARS_PRICE_1_MONTH", "int", "pricing", "Цена 1 мес. (Stars)"),
    SettingField("STARS_PRICE_3_MONTHS", "int", "pricing", "Цена 3 мес. (Stars)"),
    SettingField("STARS_PRICE_6_MONTHS", "int", "pricing", "Цена 6 мес. (Stars)"),
    SettingField("STARS_PRICE_12_MONTHS", "int", "pricing", "Цена 12 мес. (Stars)"),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_1_MONTH",
        "int",
        "pricing",
        "Бонус приглашающему: 1 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_3_MONTHS",
        "int",
        "pricing",
        "Бонус приглашающему: 3 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_6_MONTHS",
        "int",
        "pricing",
        "Бонус приглашающему: 6 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_12_MONTHS",
        "int",
        "pricing",
        "Бонус приглашающему: 12 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_1_MONTH",
        "int",
        "pricing",
        "Бонус приглашённому: 1 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS",
        "int",
        "pricing",
        "Бонус приглашённому: 3 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS",
        "int",
        "pricing",
        "Бонус приглашённому: 6 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS",
        "int",
        "pricing",
        "Бонус приглашённому: 12 мес.",
        min=0,
        subsection="legacy_tariffs",
    ),
    SettingField(
        "TRAFFIC_PACKAGES", "string", "pricing", "Пакеты трафика", "Формат: 10:199,50:799 (ГБ:цена)"
    ),
    SettingField("STARS_TRAFFIC_PACKAGES", "string", "pricing", "Пакеты трафика (Stars)"),
    SettingField(
        "SUBSCRIPTION_PURCHASE_DESCRIPTION_ENABLED",
        "bool",
        "payments",
        "Показывать описание подписки",
        "Текст появится перед выбором срока покупки или продления.",
        subsection="checkout",
    ),
    SettingField(
        "SUBSCRIPTION_PURCHASE_DESCRIPTION_RU",
        "text",
        "payments",
        "Описание подписки (RU)",
        "Русская версия текста на этапе оплаты.",
        subsection="checkout",
    ),
    SettingField(
        "SUBSCRIPTION_PURCHASE_DESCRIPTION_EN",
        "text",
        "payments",
        "Описание подписки (EN)",
        "Английская версия текста на этапе оплаты.",
        subsection="checkout",
    ),
    SettingField(
        "PAYMENT_REQUEST_TIMEOUT_SECONDS",
        "float",
        "payments",
        "Таймаут запроса к провайдеру",
        "Максимальное общее время одного API-запроса к платёжному провайдеру, в секундах.",
        optional=False,
        min=1,
        subsection="checkout",
    ),
    # ─── Payment providers (toggles) ───────────────────────────────
    # Common
    SettingField("STARS_ENABLED", "bool", "payments", "Telegram Stars", subsection="common"),
    SettingField(
        "STARS_ADMIN_ONLY_ENABLED",
        "bool",
        "payments",
        "Telegram Stars admin-only",
        (
            "Shows Telegram Stars only to users from ADMIN_IDS. "
            "Payment callbacks remain active for admin test payments."
        ),
        subsection="common",
        i18n_label_key="admin_settings_provider_admin_only_label",
        i18n_description_key="admin_settings_provider_admin_only_description",
    ),
    SettingField(
        "PAYMENT_METHODS_ORDER",
        "string",
        "payments",
        "Порядок методов оплаты",
        "Через запятую: severpay,freekassa,yookassa,platega,stars,cryptopay,heleket,paykilla,lava",
        subsection="common",
    ),
    # ─── Trial ─────────────────────────────────────────────────────
    SettingField(
        "TRIAL_ENABLED",
        "bool",
        "pricing",
        "Триал включён",
        optional=False,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_DURATION_DAYS",
        "int",
        "pricing",
        "Длительность триала (дней)",
        optional=False,
        min=0,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_TRAFFIC_LIMIT_GB",
        "float",
        "pricing",
        "Лимит трафика триала (ГБ)",
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
        "TRIAL_TRAFFIC_STRATEGY",
        "string",
        "pricing",
        "Стратегия сброса трафика триала",
        optional=False,
        choices=TRAFFIC_STRATEGY_CHOICES,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_WITHOUT_TELEGRAM_ENABLED",
        "bool",
        "pricing",
        "Триал без Telegram",
        (
            "Если выключено, email-only пользователю нужно привязать Telegram для "
            "активации триала. Disposable email домены всегда требуют Telegram."
        ),
        optional=False,
        subsection="trial",
    ),
    SettingField(
        "TRIAL_SQUAD_UUIDS",
        "string",
        "pricing",
        "Internal Squads для триала",
        "UUID через запятую. Если пусто, используется USER_SQUAD_UUIDS.",
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
        "REFERRAL_ONE_BONUS_PER_REFEREE",
        "bool",
        "pricing",
        "Бонусы только за первый платёж приглашённого",
        (
            "Если включено, повторные покупки того же приглашённого пользователя больше не "
            "начисляют реферальные бонусы ни ему, ни пригласившему. Первый успешный платёж "
            "остаётся бонусным."
        ),
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_WELCOME_BONUS_DAYS",
        "int",
        "pricing",
        "Приветственный бонус (дней)",
        min=0,
        subsection="referral",
    ),
    SettingField(
        "REFERRAL_WELCOME_BONUS_WITHOUT_TELEGRAM_ENABLED",
        "bool",
        "pricing",
        "Приветственный бонус без Telegram",
        (
            "Если выключено, email-only пользователю нужно привязать Telegram для получения "
            "реферального приветственного бонуса. Disposable email домены всегда требуют Telegram."
        ),
        subsection="referral",
    ),
    SettingField(
        "LEGACY_REFS",
        "bool",
        "pricing",
        "Legacy ref-ссылки с ID пользователя",
        (
            "Принимать старые ссылки вида /start ref_<telegram_id>, где payload содержит "
            "Telegram/user ID пригласившего."
        ),
        subsection="legacy_tariffs",
    ),
    SettingField(
        "DISPOSABLE_EMAIL_DOMAINS",
        "text",
        "pricing",
        "Disposable email домены",
        (
            "Домены по одному на строку или через запятую. Пользователи без Telegram с такими "
            "email не смогут получить trial или реферальный приветственный бонус."
        ),
        placeholder="mailinator.com\ntemp-mail.org\nyopmail.com",
        subsection="referral",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_REFERRAL_CODE_COMPAT_ENABLED",
        "bool",
        "migrations",
        "Старые ref-ссылки Remnashop",
        "Принимать импортированные ref-коды Remnashop вместе с текущими кодами пользователей.",
        subsection="Remnashop",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_PROMO_CODE_COMPAT_ENABLED",
        "bool",
        "migrations",
        "Старые промокоды Remnashop",
        "Пробовать точное совпадение промокода перед обычной uppercase-нормализацией.",
        subsection="Remnashop",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_IMPORTED_AT",
        "string",
        "migrations",
        "Последний импорт Remnashop",
        "Заполняется скриптом импорта. Можно очистить, если отметка больше не нужна.",
        subsection="Remnashop",
    ),
    SettingField(
        "MIGRATION_REMNASHOP_NOTES",
        "text",
        "migrations",
        "Заметки по миграции Remnashop",
        "Внутренние заметки оператора по перенесенному инстансу.",
        subsection="Remnashop",
    ),
    # ─── Notifications ─────────────────────────────────────────────
    SettingField(
        "SUBSCRIPTION_NOTIFICATIONS_ENABLED",
        "bool",
        "notifications",
        "Включены уведомления о подписке",
    ),
    SettingField(
        "SUBSCRIPTION_EMAIL_NOTIFICATIONS_ENABLED",
        "bool",
        "notifications",
        "Дублировать уведомления о подписке на email",
        "Письма отправляются только пользователям с привязанным email и рабочим SMTP.",
    ),
    SettingField(
        "SUBSCRIPTION_NOTIFY_ON_EXPIRE", "bool", "notifications", "Уведомлять об истечении"
    ),
    SettingField(
        "SUBSCRIPTION_NOTIFY_AFTER_EXPIRE", "bool", "notifications", "Уведомлять после истечения"
    ),
    SettingField(
        "SUBSCRIPTION_NOTIFY_DAYS_BEFORE",
        "int",
        "notifications",
        "За сколько дней предупреждать",
        min=0,
    ),
    SettingField(
        "SUBSCRIPTION_NOTIFY_HOURS_BEFORE",
        "int",
        "notifications",
        "За сколько часов предупреждать",
        min=0,
        max=23,
    ),
    SettingField("LOG_NEW_USERS", "bool", "notifications", "Логировать новых пользователей"),
    SettingField("LOG_PAYMENTS", "bool", "notifications", "Логировать платежи"),
    SettingField("LOG_SUPPORT", "bool", "notifications", "Логировать тикеты поддержки"),
    SettingField(
        "LOG_PROMO_ACTIVATIONS", "bool", "notifications", "Логировать активации промокодов"
    ),
    SettingField("LOG_TRIAL_ACTIVATIONS", "bool", "notifications", "Логировать активации триала"),
    SettingField(
        "LOG_SUSPICIOUS_ACTIVITY", "bool", "notifications", "Логировать подозрительные действия"
    ),
    SettingField(
        "LOG_ADMIN_ACTIONS",
        "bool",
        "notifications",
        "Логировать действия администраторов",
        "Если выключено, события от пользователей из ADMIN_IDS не записываются в message logs.",
        i18n_label_key="admin_settings_field_log_admin_actions_label",
        i18n_description_key="admin_settings_field_log_admin_actions_description",
    ),
    SettingField(
        "LOG_LEVEL",
        "string",
        "notifications",
        "Глобальный уровень логов",
        "DEBUG / INFO / WARNING / ERROR",
    ),
    SettingField("LOG_CHAT_ID", "int", "notifications", "ID чата для логов"),
    SettingField("LOG_THREAD_ID", "int", "notifications", "ID треда (для супергрупп)"),
    SettingField(
        "LOG_SUPPORT_THREAD_ID",
        "int",
        "notifications",
        "ID треда поддержки",
        "Тред лог-чата для уведомлений о тикетах поддержки.",
    ),
    SettingField(
        "BACKUP_ENABLED",
        "bool",
        "backups",
        "Бэкапы включены",
        "Worker будет периодически собирать ZIP-архив и отправлять его в Telegram.",
    ),
    SettingField(
        "BACKUP_CHAT_ID",
        "int",
        "backups",
        "ID чата для бэкапов",
        "Куда отправлять ZIP-архивы. Если пусто, используется LOG_CHAT_ID.",
    ),
    SettingField(
        "BACKUP_THREAD_ID",
        "int",
        "backups",
        "ID треда для бэкапов",
        "Необязательный topic/thread ID. Если пусто, используется LOG_THREAD_ID.",
    ),
    SettingField(
        "BACKUP_INTERVAL_SECONDS",
        "int",
        "backups",
        "Период бэкапов (сек.)",
        "По умолчанию 3600: запуск на границе часа (12:00, 13:00 и т.д.).",
        optional=False,
        min=60,
    ),
    SettingField(
        "BACKUP_LOCAL_RETENTION",
        "int",
        "backups",
        "Сколько архивов хранить",
        "Сколько последних ZIP-архивов оставлять в data/backups на сервере.",
        optional=False,
        min=1,
    ),
    SettingField(
        "BACKUP_COMPOSE_ENABLED",
        "bool",
        "backups",
        "Добавлять compose-папку",
        (
            "Добавляет snapshot /app/compose-source. Если папка не смонтирована, "
            "бэкап БД все равно будет создан."
        ),
    ),
    SettingField(
        "SUPPORT_TICKETS_ENABLED",
        "bool",
        "support",
        "Тикеты поддержки включены",
        "Показывает раздел поддержки в ЛК и включает создание тикетов.",
    ),
    SettingField(
        "SUPPORT_ADMIN_EMAIL_NOTIFICATIONS_ENABLED",
        "bool",
        "support",
        "Email-уведомления админам",
        (
            "Если выключено, новые тикеты и ответы пользователей останутся "
            "только в Telegram и лог-чате."
        ),
    ),
    SettingField(
        "SUPPORT_ADMIN_NOTIFICATION_COOLDOWN_SECONDS",
        "int",
        "support",
        "Пауза Telegram-уведомлений",
        (
            "Минимум секунд между повторными Telegram/log уведомлениями "
            "по одному непрочитанному тикету."
        ),
        min=0,
    ),
    SettingField(
        "SUPPORT_ADMIN_EMAIL_COOLDOWN_SECONDS",
        "int",
        "support",
        "Пауза email-уведомлений",
        "Минимум секунд между повторными email-уведомлениями по одному непрочитанному тикету.",
        min=0,
    ),
    SettingField(
        "SUPPORT_TICKET_MAX_BODY_LENGTH",
        "int",
        "support",
        "Макс. длина сообщения",
        "Максимальное количество символов в сообщении тикета.",
        min=1,
    ),
    SettingField(
        "SUPPORT_TICKET_MAX_SUBJECT_LENGTH",
        "int",
        "support",
        "Макс. длина темы",
        "Максимальное количество символов в теме тикета.",
        min=1,
    ),
    SettingField(
        "SUPPORT_TICKET_RATE_LIMIT_PER_HOUR",
        "int",
        "support",
        "Лимит тикетов в час",
        "Сколько новых тикетов пользователь может создать за час. 0 — без лимита.",
        min=0,
    ),
    # ─── Devices ───────────────────────────────────────────────────
    SettingField("MY_DEVICES_SECTION_ENABLED", "bool", "devices", "Раздел «Мои устройства»"),
    SettingField(
        "USER_HWID_DEVICE_LIMIT", "int", "devices", "Лимит устройств по умолчанию (0 = ∞)", min=0
    ),
    SettingField("USER_TRAFFIC_LIMIT_GB", "float", "devices", "Лимит трафика пользователя (ГБ)"),
    SettingField(
        "USER_TRAFFIC_STRATEGY",
        "string",
        "devices",
        "Стратегия сброса трафика",
        choices=TRAFFIC_STRATEGY_CHOICES,
    ),
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
        "Анонимная статистика установки",
        "Раз в сутки отправляет обезличенный сигнал: версия, маркер образа "
        "official/custom, ОС, локаль и число пользователей в виде диапазона. Без персональных "
        "данных, токенов и доменов. Помогает понять число активных установок, какие "
        "версии используются и долю изменённых сборок. Можно отключить здесь без "
        "перезапуска.",
    ),
]
