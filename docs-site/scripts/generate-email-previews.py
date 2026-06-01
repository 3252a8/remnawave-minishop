import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from bot.services.email_templates import (  # noqa: E402
    render_account_merged,
    render_login_code,
    render_payment_success,
    render_subscription_expiring,
    render_subscription_lifecycle_notification,
    render_support_admin_reply_user,
    render_support_new_ticket_admin,
    render_support_ticket_closed_user,
    render_support_user_reply_admin,
    render_user_notification,
)

LANGUAGE = "ru"


class PreviewI18n:
    def __init__(self, path: Path, default: str = "ru"):
        self.default_lang = default
        self.locales_data = {}
        for item in path.glob("*.json"):
            try:
                data = json.loads(item.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                self.locales_data[item.stem] = {
                    str(key): str(value) for key, value in data.items() if isinstance(value, str)
                }

    def gettext(self, lang_code: str | None, key: str, **kwargs) -> str:
        requested = str(lang_code or "").strip().lower().replace("_", "-")
        requested_base = requested.split("-", 1)[0]
        if requested in self.locales_data:
            messages = self.locales_data[requested]
        elif requested_base in self.locales_data:
            messages = self.locales_data[requested_base]
        else:
            messages = self.locales_data.get(self.default_lang) or self.locales_data.get("en", {})
        template = messages.get(key)
        if template is None and self.default_lang in self.locales_data:
            template = self.locales_data[self.default_lang].get(key)
        if template is None:
            template = key
        try:
            return template.format(**kwargs) if kwargs else template
        except Exception:
            return template


def settings():
    return SimpleNamespace(
        DEFAULT_LANGUAGE=LANGUAGE,
        EMAIL_CODE_TTL_SECONDS=600,
        WEBAPP_LOGO_URL="",
        WEBAPP_LOGO_USE_EMOJI=False,
        WEBAPP_PRIMARY_COLOR="#00fe7a",
        WEBAPP_TITLE="remnawave-minishop",
    )


I18N = PreviewI18n(REPO_ROOT / "locales", default=LANGUAGE)
SETTINGS = settings()
SAMPLE = {
    "amount": 390,
    "code": "483921",
    "currency": "RUB",
    "dashboard_url": "https://mini.example.com/app",
    "end_date": "21.06.2026, 18:00",
    "magic_url": "https://mini.example.com/app/auth/magic/preview",
    "premium_traffic": 25,
    "regular_traffic": 100,
    "ticket_url": "https://mini.example.com/app/support/42",
}


def t(key: str, **kwargs) -> str:
    return I18N.gettext(LANGUAGE, key, **kwargs)


def preview(item_id: str, category: str, title: str, content):
    return {
        "id": item_id,
        "category": category,
        "title": title,
        "subject": content.subject,
        "html": content.html,
    }


def payment_preview(
    item_id: str,
    title: str,
    sale_mode: str,
    *,
    months: int = 0,
    traffic_gb: float | None = None,
):
    return preview(
        item_id,
        "Платежи",
        title,
        render_payment_success(
            SETTINGS,
            language_code=LANGUAGE,
            sale_mode=sale_mode,
            months=months,
            traffic_gb=traffic_gb,
            amount=SAMPLE["amount"],
            currency=SAMPLE["currency"],
            end_date_text=SAMPLE["end_date"],
            dashboard_url=SAMPLE["dashboard_url"],
            provider_label="YooKassa",
            i18n=I18N,
        ),
    )


def user_notification_preview(
    item_id: str,
    title: str,
    subject_key: str,
    message_text: str,
    *,
    cta_label_key: str = "email_user_notification_cta",
):
    subject = t(subject_key)
    return preview(
        item_id,
        "Уведомления",
        title,
        render_user_notification(
            SETTINGS,
            language_code=LANGUAGE,
            subject=subject,
            heading=subject,
            intro=t("email_user_notification_intro"),
            message_text=message_text,
            dashboard_url=SAMPLE["dashboard_url"],
            cta_label=t(cta_label_key),
            i18n=I18N,
        ),
    )


def expiring_preview(item_id: str, title: str, days_left: int):
    return preview(
        item_id,
        "Подписка",
        title,
        render_subscription_expiring(
            SETTINGS,
            language_code=LANGUAGE,
            days_left=days_left,
            end_date_text=SAMPLE["end_date"],
            dashboard_url=SAMPLE["dashboard_url"],
            i18n=I18N,
        ),
    )


def lifecycle_preview(
    item_id: str,
    title: str,
    notification_key: str,
    message_text: str,
    *,
    mirrored_from_telegram: bool = False,
    days_left: int | None = None,
    hours_before: int | None = None,
):
    return preview(
        item_id,
        "Подписка",
        title,
        render_subscription_lifecycle_notification(
            SETTINGS,
            language_code=LANGUAGE,
            notification_key=notification_key,
            message_text=message_text,
            end_date_text=SAMPLE["end_date"],
            dashboard_url=SAMPLE["dashboard_url"],
            mirrored_from_telegram=mirrored_from_telegram,
            days_left=days_left,
            hours_before=hours_before,
            i18n=I18N,
        ),
    )


def support_snapshot_rows():
    return [
        ("email_support_row_tariff", "Premium"),
        ("email_support_row_remaining", "3 д. 4 ч."),
    ]


EMAIL_PREVIEWS = [
    preview(
        "login-code",
        "Доступ",
        "Код для входа",
        render_login_code(
            SETTINGS,
            code=SAMPLE["code"],
            language_code=LANGUAGE,
            magic_link=SAMPLE["magic_url"],
            purpose="login",
            i18n=I18N,
        ),
    ),
    preview(
        "set-password-code",
        "Доступ",
        "Код для создания пароля",
        render_login_code(
            SETTINGS,
            code=SAMPLE["code"],
            language_code=LANGUAGE,
            purpose="set_password",
            i18n=I18N,
        ),
    ),
    preview(
        "account-merged",
        "Аккаунт",
        "Аккаунты объединены",
        render_account_merged(
            SETTINGS,
            language_code=LANGUAGE,
            primary_user_id=100200300,
            removed_user_id=-42,
            final_end_date_text=SAMPLE["end_date"],
            i18n=I18N,
        ),
    ),
    payment_preview(
        "payment-subscription",
        "Оплата подписки",
        "subscription",
        months=1,
    ),
    payment_preview(
        "payment-traffic",
        "Покупка трафика",
        "traffic",
        traffic_gb=SAMPLE["regular_traffic"],
    ),
    payment_preview(
        "payment-premium-traffic",
        "Покупка premium-трафика",
        "premium_topup",
        traffic_gb=SAMPLE["premium_traffic"],
    ),
    payment_preview("payment-hwid", "Покупка HWID-устройств", "hwid_device", months=2),
    payment_preview("payment-tariff-upgrade", "Платное повышение тарифа", "tariff_upgrade"),
    user_notification_preview(
        "payment-failed",
        "Неуспешная оплата",
        "email_payment_failed_subject",
        "Платеж не был завершен. Можно попробовать еще раз из личного кабинета.",
    ),
    user_notification_preview(
        "payment-method-bound",
        "Способ оплаты привязан",
        "email_payment_method_bound_subject",
        "Автопродление подключено, следующий платеж пройдет автоматически.",
    ),
    user_notification_preview(
        "referral-bonus",
        "Реферальный бонус",
        "email_referral_bonus_subject",
        "Друг активировал подписку, и бонусные дни уже добавлены к вашему аккаунту.",
    ),
    user_notification_preview(
        "trial-traffic-depleted",
        "Трафик пробного периода закончился",
        "email_trial_traffic_depleted_subject",
        "Пробный трафик израсходован. Оформите подписку, чтобы продолжить пользоваться сервисом.",
    ),
    user_notification_preview(
        "regular-traffic-almost",
        "Обычный трафик почти закончился",
        "email_traffic_warning_regular_almost_subject",
        "Использовано больше 85% трафика тарифа. Можно докупить пакет заранее.",
        cta_label_key="email_traffic_warning_regular_cta",
    ),
    user_notification_preview(
        "regular-traffic-depleted",
        "Обычный трафик закончился",
        "email_traffic_warning_regular_depleted_subject",
        "Трафик тарифа израсходован. Докупите пакет, чтобы восстановить доступ.",
        cta_label_key="email_traffic_warning_regular_cta",
    ),
    user_notification_preview(
        "premium-traffic-almost",
        "Premium-трафик почти закончился",
        "email_traffic_warning_premium_almost_subject",
        "Premium-трафика осталось мало. Можно докупить пакет до полного расхода.",
        cta_label_key="email_traffic_warning_premium_cta",
    ),
    user_notification_preview(
        "premium-traffic-depleted",
        "Premium-трафик закончился",
        "email_traffic_warning_premium_depleted_subject",
        (
            "Premium-трафик израсходован. Докупите пакет, "
            "чтобы продолжить использовать premium-маршруты."
        ),
        cta_label_key="email_traffic_warning_premium_cta",
    ),
    expiring_preview(
        "subscription-expiring-today",
        "Подписка заканчивается сегодня",
        0,
    ),
    expiring_preview(
        "subscription-expiring-tomorrow",
        "Подписка заканчивается завтра",
        1,
    ),
    expiring_preview(
        "subscription-expiring-days",
        "Подписка скоро закончится",
        3,
    ),
    lifecycle_preview(
        "lifecycle-before-days",
        "Lifecycle: осталось несколько дней",
        "before_days",
        "Подписка скоро закончится. Продлите ее заранее, чтобы доступ не прерывался.",
        days_left=3,
    ),
    lifecycle_preview(
        "lifecycle-before-hours",
        "Lifecycle: осталось несколько часов",
        "before_hours",
        "До окончания подписки осталось несколько часов.",
        hours_before=6,
    ),
    lifecycle_preview(
        "lifecycle-expired",
        "Lifecycle: подписка закончилась",
        "expired",
        "Подписка закончилась. Продлите доступ в личном кабинете.",
    ),
    lifecycle_preview(
        "lifecycle-expired-after",
        "Lifecycle: подписка закончилась вчера",
        "expired_24h_after",
        "Вчера подписка была отключена. Вы можете восстановить доступ продлением.",
    ),
    lifecycle_preview(
        "lifecycle-autorenew",
        "Lifecycle: автопродление завтра",
        "before_2d_autorenew",
        "Завтра будет выполнено автопродление подписки.",
    ),
    lifecycle_preview(
        "lifecycle-mirrored",
        "Lifecycle: копия Telegram-уведомления",
        "before_days",
        "Это письмо дублирует важное уведомление, отправленное в Telegram.",
        mirrored_from_telegram=True,
        days_left=2,
    ),
    preview(
        "support-new-ticket-admin",
        "Поддержка",
        "Новый тикет для администратора",
        render_support_new_ticket_admin(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            user_display="alex@example.com",
            subject="Не работает подключение",
            body_preview="Пользователь не может подключиться после продления.",
            snapshot_rows=support_snapshot_rows(),
            ticket_url="https://mini.example.com/app/admin/support/42",
        ),
    ),
    preview(
        "support-user-reply-admin",
        "Поддержка",
        "Ответ пользователя для администратора",
        render_support_user_reply_admin(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            user_display="alex@example.com",
            subject="Не работает подключение",
            body_preview="Проблема повторилась на телефоне и ноутбуке.",
            snapshot_rows=support_snapshot_rows(),
            ticket_url="https://mini.example.com/app/admin/support/42",
        ),
    ),
    preview(
        "support-admin-reply-user",
        "Поддержка",
        "Ответ поддержки пользователю",
        render_support_admin_reply_user(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            subject="Не работает подключение",
            body_preview="Мы обновили конфигурацию. Попробуйте подключиться еще раз.",
            ticket_url=SAMPLE["ticket_url"],
        ),
    ),
    preview(
        "support-ticket-closed-user",
        "Поддержка",
        "Тикет закрыт",
        render_support_ticket_closed_user(
            SETTINGS,
            I18N,
            LANGUAGE,
            ticket_id=42,
            subject="Не работает подключение",
            ticket_url=SAMPLE["ticket_url"],
        ),
    ),
]

print(json.dumps(EMAIL_PREVIEWS, ensure_ascii=False))
