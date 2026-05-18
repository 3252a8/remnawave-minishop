"""Manifest of settings editable from the admin web app.

Each entry describes a single overridable attribute on the global
``Settings`` instance. The manifest is the only contract between the
admin UI and the backend: keys not listed here cannot be changed via
the API, even by an admin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple


@dataclass(frozen=True)
class SettingField:
    key: str
    type: str  # "string" | "int" | "float" | "bool" | "text" | "url" | "color" | "icon"
    section: str
    label: str
    description: str = ""
    placeholder: str = ""
    optional: bool = True
    secret: bool = False
    min: Optional[float] = None
    max: Optional[float] = None
    choices: Optional[Tuple[Tuple[str, str], ...]] = None
    subsection: Optional[str] = None  # group label inside a section
    i18n_label_key: Optional[str] = None
    i18n_description_key: Optional[str] = None


def _payment_presentation_fields(
    method_key: str,
    subsection: str,
    *,
    default_icon: str,
) -> List[SettingField]:
    prefix = f"PAYMENT_{method_key}"
    return [
        SettingField(
            f"{prefix}_WEBAPP_LABEL_RU",
            "string",
            "payments",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            subsection=subsection,
        ),
        SettingField(
            f"{prefix}_WEBAPP_LABEL_EN",
            "string",
            "payments",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            subsection=subsection,
        ),
        SettingField(
            f"{prefix}_WEBAPP_ICON",
            "icon",
            "payments",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            subsection=subsection,
            placeholder=default_icon,
        ),
        SettingField(
            f"{prefix}_TELEGRAM_LABEL_RU",
            "string",
            "payments",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            subsection=subsection,
        ),
        SettingField(
            f"{prefix}_TELEGRAM_LABEL_EN",
            "string",
            "payments",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            subsection=subsection,
        ),
        SettingField(
            f"{prefix}_TELEGRAM_EMOJI",
            "string",
            "payments",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            subsection=subsection,
            placeholder="💳",
        ),
    ]


SETTINGS_MANIFEST: List[SettingField] = [
    # ─── General ────────────────────────────────────────────────────
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
    SettingField("TERMS_OF_SERVICE_URL", "url", "general", "Условия использования"),
    SettingField("PRIVACY_POLICY_URL", "url", "general", "Политика конфиденциальности"),
    SettingField("USER_AGREEMENT_URL", "url", "general", "Пользовательское соглашение"),
    SettingField("DISABLE_WELCOME_MESSAGE", "bool", "general", "Скрыть приветствие /start"),
    SettingField(
        "START_COMMAND_DESCRIPTION", "string", "general", "Описание /start", placeholder=""
    ),
    SettingField(
        "REQUIRED_CHANNEL_ID",
        "int",
        "general",
        "ID обязательного канала",
        "Telegram ID канала, в котором нужно состоять.",
    ),
    SettingField(
        "REQUIRED_CHANNEL_LINK",
        "string",
        "general",
        "Ссылка на канал",
        "Имя пользователя или invite-link.",
    ),
    # ─── Web app appearance ────────────────────────────────────────
    SettingField(
        "WEBAPP_TITLE", "string", "appearance", "Название Web App", placeholder="Моя подписка"
    ),
    SettingField(
        "WEBAPP_PRIMARY_COLOR", "color", "appearance", "Основной цвет", placeholder="#00fe7a"
    ),
    SettingField("WEBAPP_LOGO_USE_EMOJI", "bool", "appearance", "Использовать эмоджи-логотип"),
    SettingField("WEBAPP_LOGO_URL", "url", "appearance", "URL логотипа"),
    SettingField("WEBAPP_LOGO_EMOJI", "string", "appearance", "Эмоджи-логотип", placeholder="🫥"),
    SettingField(
        "WEBAPP_LOGO_EMOJI_FONT",
        "string",
        "appearance",
        "Шрифт эмоджи-логотипа",
        "Выберите шрифт для отображения эмодзи-логотипа",
        choices=(
            ("system", "Системный (по умолчанию)"),
            ("noto-color", "Noto Color Emoji"),
            ("noto-color-animated", "Noto Color Emoji Animated"),
            ("noto-emoji", "Noto Emoji"),
            ("twemoji", "Twitter Emoji"),
            ("openmoji", "OpenMoji"),
            ("apple", "Apple Color Emoji (local)"),
            ("segoe", "Segoe UI Emoji (local)"),
            ("noto-local", "Noto Emoji (local)"),
        ),
    ),
    SettingField(
        "WEBAPP_FAVICON_USE_CUSTOM",
        "bool",
        "appearance",
        "Использовать отдельную favicon",
    ),
    SettingField("WEBAPP_FAVICON_URL", "url", "appearance", "URL отдельной favicon"),
    SettingField("WEBAPP_LOGO_FAVICON_URL", "url", "appearance", "Favicon из логотипа"),
    SettingField("WEBAPP_ENABLED", "bool", "appearance", "Web App включён"),
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
        "TRAFFIC_PACKAGES", "string", "pricing", "Пакеты трафика", "Формат: 10:199,50:799 (ГБ:цена)"
    ),
    SettingField("STARS_TRAFFIC_PACKAGES", "string", "pricing", "Пакеты трафика (Stars)"),
    SettingField(
        "PAYMENT_METHODS_ORDER",
        "string",
        "pricing",
        "Порядок методов оплаты",
        "Через запятую, например: severpay,freekassa,yookassa",
    ),
    # ─── Payment providers (toggles) ───────────────────────────────
    # Common
    SettingField("STARS_ENABLED", "bool", "payments", "Telegram Stars", subsection="Общие"),
    SettingField(
        "PAYMENT_METHODS_ORDER",
        "string",
        "payments",
        "Порядок методов оплаты",
        "Через запятую: severpay,freekassa,yookassa,platega,stars,cryptopay",
        subsection="Общие",
    ),
    # YooKassa
    SettingField("YOOKASSA_ENABLED", "bool", "payments", "Включена", subsection="YooKassa"),
    SettingField("YOOKASSA_SHOP_ID", "string", "payments", "Shop ID", subsection="YooKassa"),
    SettingField(
        "YOOKASSA_SECRET_KEY",
        "string",
        "payments",
        "Secret key",
        subsection="YooKassa",
        secret=True,
    ),
    SettingField("YOOKASSA_RETURN_URL", "url", "payments", "Return URL", subsection="YooKassa"),
    SettingField(
        "YOOKASSA_DEFAULT_RECEIPT_EMAIL",
        "string",
        "payments",
        "Email для чека по умолчанию",
        subsection="YooKassa",
    ),
    SettingField(
        "YOOKASSA_VAT_CODE",
        "int",
        "payments",
        "VAT code",
        "1..6 в зависимости от системы налогообложения",
        subsection="YooKassa",
        min=1,
        max=6,
    ),
    SettingField(
        "YOOKASSA_AUTOPAYMENTS_ENABLED",
        "bool",
        "payments",
        "Автоплатежи (recurring)",
        subsection="YooKassa",
    ),
    SettingField(
        "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING",
        "bool",
        "payments",
        "Принудительная привязка карты",
        subsection="YooKassa",
    ),
    *_payment_presentation_fields("YOOKASSA", "YooKassa", default_icon="CreditCard"),
    # Platega
    SettingField("PLATEGA_ENABLED", "bool", "payments", "Включена", subsection="Platega"),
    SettingField(
        "PLATEGA_BASE_URL",
        "url",
        "payments",
        "Base URL",
        placeholder="https://app.platega.io",
        subsection="Platega",
    ),
    SettingField("PLATEGA_MERCHANT_ID", "string", "payments", "Merchant ID", subsection="Platega"),
    SettingField(
        "PLATEGA_SECRET", "string", "payments", "Secret", subsection="Platega", secret=True
    ),
    SettingField(
        "PLATEGA_PAYMENT_METHOD", "int", "payments", "Метод оплаты (legacy)", subsection="Platega"
    ),
    SettingField("PLATEGA_SBP_ENABLED", "bool", "payments", "SBP-кнопка", subsection="Platega"),
    SettingField("PLATEGA_SBP_METHOD", "int", "payments", "SBP method ID", subsection="Platega"),
    SettingField(
        "PLATEGA_CRYPTO_ENABLED", "bool", "payments", "Crypto-кнопка", subsection="Platega"
    ),
    SettingField(
        "PLATEGA_CRYPTO_METHOD", "int", "payments", "Crypto method ID", subsection="Platega"
    ),
    SettingField("PLATEGA_RETURN_URL", "url", "payments", "Return URL", subsection="Platega"),
    SettingField("PLATEGA_FAILED_URL", "url", "payments", "Failed URL", subsection="Platega"),
    *_payment_presentation_fields("PLATEGA_SBP", "Platega SBP", default_icon="CreditCard"),
    *_payment_presentation_fields("PLATEGA_CRYPTO", "Platega Crypto", default_icon="Bitcoin"),
    # ─── Trial ─────────────────────────────────────────────────────
    SettingField("TRIAL_ENABLED", "bool", "trial", "Триал включён"),
    SettingField("TRIAL_DURATION_DAYS", "int", "trial", "Длительность триала (дней)", min=0),
    SettingField("TRIAL_TRAFFIC_LIMIT_GB", "float", "trial", "Лимит трафика триала (ГБ)", min=0),
    SettingField("TRIAL_TRAFFIC_STRATEGY", "string", "trial", "Стратегия сброса трафика триала"),
    # ─── Referral program ──────────────────────────────────────────
    SettingField(
        "REFERRAL_ONE_BONUS_PER_REFEREE", "bool", "referral", "Один бонус на приглашённого"
    ),
    SettingField(
        "REFERRAL_WELCOME_BONUS_DAYS", "int", "referral", "Приветственный бонус (дней)", min=0
    ),
    SettingField("LEGACY_REFS", "bool", "referral", "Поддержка старых ref-ссылок"),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_1_MONTH",
        "int",
        "referral",
        "Бонус приглашающему: 1 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_3_MONTHS",
        "int",
        "referral",
        "Бонус приглашающему: 3 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_6_MONTHS",
        "int",
        "referral",
        "Бонус приглашающему: 6 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_INVITER_12_MONTHS",
        "int",
        "referral",
        "Бонус приглашающему: 12 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_1_MONTH",
        "int",
        "referral",
        "Бонус приглашённому: 1 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_3_MONTHS",
        "int",
        "referral",
        "Бонус приглашённому: 3 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_6_MONTHS",
        "int",
        "referral",
        "Бонус приглашённому: 6 мес.",
        min=0,
    ),
    SettingField(
        "REFERRAL_BONUS_DAYS_REFEREE_12_MONTHS",
        "int",
        "referral",
        "Бонус приглашённому: 12 мес.",
        min=0,
    ),
    # ─── Notifications ─────────────────────────────────────────────
    SettingField(
        "SUBSCRIPTION_NOTIFICATIONS_ENABLED",
        "bool",
        "notifications",
        "Включены уведомления о подписке",
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
    SettingField("LOG_NEW_USERS", "bool", "notifications", "Логировать новых пользователей"),
    SettingField("LOG_PAYMENTS", "bool", "notifications", "Логировать платежи"),
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
        i18n_label_key="settings_field_log_admin_actions_label",
        i18n_description_key="settings_field_log_admin_actions_description",
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
    # ─── Devices ───────────────────────────────────────────────────
    SettingField("MY_DEVICES_SECTION_ENABLED", "bool", "devices", "Раздел «Мои устройства»"),
    SettingField(
        "USER_HWID_DEVICE_LIMIT", "int", "devices", "Лимит устройств по умолчанию (0 = ∞)", min=0
    ),
    SettingField("USER_TRAFFIC_LIMIT_GB", "float", "devices", "Лимит трафика пользователя (ГБ)"),
    SettingField("USER_TRAFFIC_STRATEGY", "string", "devices", "Стратегия сброса трафика"),
]


def _provider_field_to_setting_field(
    spec: Any, manifest_field: Any
) -> SettingField:
    return SettingField(
        key=manifest_field.key,
        type=manifest_field.type,
        section="payments",
        label=manifest_field.label,
        description=manifest_field.description,
        placeholder=manifest_field.placeholder,
        optional=manifest_field.optional,
        secret=manifest_field.secret,
        min=manifest_field.min,
        max=manifest_field.max,
        choices=tuple(manifest_field.choices) if manifest_field.choices else None,
        subsection=manifest_field.subsection,
    )


def aggregated_manifest() -> List[SettingField]:
    """SETTINGS_MANIFEST + per-provider fragments declared in provider SPECs."""
    from bot.payment_providers import iter_provider_manifest_fields  # local to avoid cycle

    fields: List[SettingField] = list(SETTINGS_MANIFEST)
    for spec, manifest_field in iter_provider_manifest_fields():
        fields.append(_provider_field_to_setting_field(spec, manifest_field))
    return fields


def get_field_by_key(key: str) -> Optional[SettingField]:
    for field in aggregated_manifest():
        if field.key == key:
            return field
    return None


def manifest_keys() -> List[str]:
    return [f.key for f in aggregated_manifest()]


def coerce_value(field: SettingField, raw: Any) -> Any:
    """Coerce a value coming from JSON to the type declared by the field."""

    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None

    if field.type == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, (int, float)):
            return bool(raw)
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return bool(raw)

    if field.type == "int":
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.key}: integer expected") from exc
        if field.min is not None and value < field.min:
            raise ValueError(f"{field.key}: must be >= {field.min:g}")
        if field.max is not None and value > field.max:
            raise ValueError(f"{field.key}: must be <= {field.max:g}")
        return value

    if field.type == "float":
        try:
            value = float(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.key}: number expected") from exc
        if field.min is not None and value < field.min:
            raise ValueError(f"{field.key}: must be >= {field.min:g}")
        if field.max is not None and value > field.max:
            raise ValueError(f"{field.key}: must be <= {field.max:g}")
        return value

    if isinstance(raw, str):
        return raw.strip()
    return str(raw)


def manifest_payload() -> List[dict]:
    """Serialize the manifest for the admin UI."""

    sections_order = {
        "general": 1,
        "appearance": 2,
        "pricing": 3,
        "payments": 4,
        "trial": 5,
        "referral": 6,
        "notifications": 7,
        "devices": 8,
    }
    items: List[dict] = []
    for field in aggregated_manifest():
        auto_label_i18n_key = f"settings_field_{field.key.lower()}_label"
        auto_description_i18n_key = f"settings_field_{field.key.lower()}_description"
        item = {
            "key": field.key,
            "type": field.type,
            "section": field.section,
            "section_order": sections_order.get(field.section, 99),
            "subsection": field.subsection,
            "label": field.label,
            "description": field.description,
            "i18n_label_key": field.i18n_label_key or auto_label_i18n_key,
            "i18n_description_key": field.i18n_description_key
            or (auto_description_i18n_key if field.description else None),
            "placeholder": field.placeholder,
            "optional": field.optional,
            "secret": field.secret,
        }
        if field.choices:
            item["choices"] = [{"value": v, "label": lbl} for v, lbl in field.choices]
        items.append(item)
    return items
