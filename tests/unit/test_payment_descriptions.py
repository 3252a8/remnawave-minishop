from pathlib import Path

from bot.app.web.webapp.billing_payments import _localized_payment_description
from bot.middlewares.i18n import JsonI18n

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_webapp_payment_descriptions_use_shared_localized_copy() -> None:
    i18n = JsonI18n(str(REPO_ROOT / "locales"), default="en")
    cases: tuple[tuple[str, object, str, float | None, str], ...] = (
        ("ru", 12, "subscription", None, "Оплата подписки на 12 мес."),
        ("en", 12, "subscription", None, "Subscription payment for 12 mo."),
        ("ru", 12.5, "traffic", 12.5, "Пакет трафика 12.5 ГБ"),
        ("en", 12.5, "traffic", 12.5, "Traffic package 12.5 GB"),
        ("ru", 2, "hwid_devices", None, "Дополнительные HWID устройства +2"),
        ("en", 2, "hwid_devices", None, "Extra HWID devices +2"),
    )

    for lang, units, sale_mode, traffic_gb, expected in cases:
        assert (
            _localized_payment_description(
                i18n=i18n,
                lang=lang,
                units=units,
                sale_mode=sale_mode,
                traffic_gb=traffic_gb,
            )
            == expected
        )
