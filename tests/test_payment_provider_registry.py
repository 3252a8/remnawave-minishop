import importlib
from pathlib import Path
from types import SimpleNamespace

from bot.keyboards.inline.user_keyboards import get_payment_method_keyboard
from bot.payment_providers import (
    get_provider_spec,
    iter_provider_specs,
    iter_service_keys,
    pending_statuses,
    provider_emoji_map,
    provider_label_map,
    provider_telegram_button_text,
    resolve_provider_presentation,
)
from bot.payment_providers.shared import (
    format_number_for_payload,
    payment_record_amounts,
    sale_mode_base,
    sale_mode_is_hwid_devices,
    sale_mode_is_traffic,
    sale_mode_tariff_key,
)
from config.settings import Settings

_LEGACY_PROVIDER_FILES = [
    "backend/bot/services/yookassa_service.py",
    "backend/bot/services/freekassa_service.py",
    "backend/bot/services/platega_service.py",
    "backend/bot/services/severpay_service.py",
    "backend/bot/services/crypto_pay_service.py",
    "backend/bot/services/stars_service.py",
    "backend/bot/services/wata_service.py",
    "backend/bot/handlers/user/payment.py",
    "backend/bot/handlers/user/subscription/payment_methods.py",
    "backend/bot/handlers/user/subscription/payments_yookassa.py",
    "backend/bot/handlers/user/subscription/payments_freekassa.py",
    "backend/bot/handlers/user/subscription/payments_platega.py",
    "backend/bot/handlers/user/subscription/payments_severpay.py",
    "backend/bot/handlers/user/subscription/payments_crypto.py",
    "backend/bot/handlers/user/subscription/payments_stars.py",
    "backend/bot/handlers/user/subscription/payments_wata.py",
]

_PROVIDER_MODULES = {
    "yookassa": "YooKassaService",
    "freekassa": "FreeKassaService",
    "platega": "PlategaService",
    "severpay": "SeverPayService",
    "cryptopay": "CryptoPayService",
    "stars": "StarsService",
    "wata": "WataService",
}


def test_legacy_provider_integration_files_are_removed():
    repo_root = Path(__file__).resolve().parents[1]

    for relative_path in _LEGACY_PROVIDER_FILES:
        assert not (repo_root / relative_path).exists()


def test_every_provider_module_owns_its_service_and_spec():
    for module_name, service_class_name in _PROVIDER_MODULES.items():
        module = importlib.import_module(f"bot.payment_providers.{module_name}")

        assert hasattr(module, service_class_name)
        assert hasattr(module, "SPEC") or hasattr(module, "SPECS")


def test_wata_is_registered_as_single_provider_module():
    spec = get_provider_spec("wata")

    assert spec is not None
    assert spec.service_key == "wata_service"
    assert spec.pending_status == "pending_wata"
    assert spec.button_text_key == "pay_with_wata_button"
    assert spec.callback_prefix == "pay_wata"
    assert spec.router is not None
    assert spec.create_service is not None
    assert spec.webhook_route is not None
    assert spec.create_webapp_payment is not None


def test_yookassa_provider_keeps_autorenew_entrypoints_local():
    yookassa = importlib.import_module("bot.payment_providers.yookassa")
    spec = get_provider_spec("yookassa")

    assert spec is not None
    assert spec.service_key == "yookassa_service"
    assert spec.create_service is not None
    assert spec.webhook_route is yookassa.yookassa_webhook_route
    assert yookassa.payment_processing_lock is not None
    assert callable(yookassa.process_successful_payment)
    assert callable(yookassa.process_cancelled_payment)
    assert callable(yookassa.yookassa_webhook_route)


def test_every_payment_method_has_registry_driven_webapp_creator():
    missing = [
        spec.id
        for spec in iter_provider_specs()
        if spec.create_webapp_payment is None
    ]

    assert missing == []


def test_service_keys_and_statuses_come_from_provider_specs():
    assert set(iter_service_keys()) == {
        "yookassa_service",
        "freekassa_service",
        "platega_service",
        "severpay_service",
        "wata_service",
        "stars_service",
        "cryptopay_service",
    }
    assert set(pending_statuses()) >= {
        "pending",
        "pending_yookassa",
        "pending_freekassa",
        "pending_platega",
        "pending_severpay",
        "pending_wata",
        "pending_cryptopay",
        "pending_stars",
    }


def test_provider_labels_and_emojis_include_storage_keys_and_method_aliases():
    labels = provider_label_map()
    emojis = provider_emoji_map()

    assert labels["wata"] == "Wata"
    assert labels["telegram_stars"] == "Telegram Stars"
    assert labels["stars"] == "Telegram Stars"
    assert labels["platega"] == "Platega"
    assert labels["platega_sbp"] == "Platega"
    assert labels["platega_crypto"] == "Platega"
    assert emojis["stars"] == get_provider_spec("stars").default_telegram_emoji
    assert emojis["telegram_stars"] == get_provider_spec("stars").default_telegram_emoji
    assert emojis["cryptopay"] == get_provider_spec("cryptopay").default_telegram_emoji


def test_provider_presentation_resolves_defaults_and_overrides():
    spec = get_provider_spec("yookassa")
    assert spec is not None

    default = resolve_provider_presentation(spec)
    assert default.webapp_label == spec.webapp_label
    assert default.webapp_icon == "CreditCard"
    assert default.telegram_label == spec.telegram_labels["ru"]
    assert default.telegram_emoji == spec.default_telegram_emoji
    assert not default.telegram_customized

    settings = SimpleNamespace(
        PAYMENT_YOOKASSA_WEBAPP_LABEL_EN="Card in app",
        PAYMENT_YOOKASSA_WEBAPP_ICON="WalletCards",
        PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN="Card in bot",
        PAYMENT_YOOKASSA_TELEGRAM_EMOJI="💸",
    )
    custom = resolve_provider_presentation(spec, settings, language="en")
    assert custom.webapp_label == "Card in app"
    assert custom.webapp_icon == "WalletCards"
    assert custom.telegram_label == "Card in bot"
    assert custom.telegram_emoji == "💸"
    assert custom.telegram_customized


def test_provider_telegram_button_text_uses_provider_defaults_until_customized():
    spec = get_provider_spec("wata")
    assert spec is not None

    translate = lambda key: f"i18n:{key}"
    assert (
        provider_telegram_button_text(spec, SimpleNamespace(), translate, language="en")
        == f"{spec.default_telegram_emoji} Wata"
    )

    settings = SimpleNamespace(PAYMENT_WATA_TELEGRAM_LABEL_EN="Pay Wata")
    assert (
        provider_telegram_button_text(spec, settings, translate, language="en")
        == f"{spec.default_telegram_emoji} Pay Wata"
    )


def test_provider_presentation_ignores_cross_language_override():
    spec = get_provider_spec("yookassa")
    assert spec is not None

    settings = SimpleNamespace(PAYMENT_YOOKASSA_WEBAPP_LABEL_RU="Карта")

    assert (
        resolve_provider_presentation(spec, settings, language="en").webapp_label
        == "Bank card"
    )


def test_payment_method_keyboard_uses_custom_telegram_text_without_changing_callback():
    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="wata",
        WATA_ENABLED=True,
        PAYMENT_WATA_TELEGRAM_LABEL_EN="Wata custom",
        PAYMENT_WATA_TELEGRAM_EMOJI="💸",
    )
    i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)

    markup = get_payment_method_keyboard(
        months=1,
        price=150,
        stars_price=None,
        currency_symbol_val="RUB",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
    )

    button = markup.inline_keyboard[0][0]
    assert button.text == "💸 Wata custom"
    assert button.callback_data == "pay_wata:1:150:subscription"


def test_provider_callbacks_are_built_from_specs():
    wata = get_provider_spec("wata")
    stars = get_provider_spec("stars")

    assert wata is not None
    assert stars is not None
    assert (
        wata.callback_data(
            value="1",
            rub_price=150,
            stars_price=None,
            sale_mode="subscription",
        )
        == "pay_wata:1:150:subscription"
    )
    assert (
        stars.callback_data(
            value="1",
            rub_price=150,
            stars_price=42,
            sale_mode="subscription",
        )
        == "pay_stars:1:42:subscription"
    )
    assert stars.callback_data(
        value="1",
        rub_price=150,
        stars_price=None,
        sale_mode="subscription",
    ) is None


def test_provider_visibility_uses_service_configuration():
    spec = get_provider_spec("wata")
    assert spec is not None

    settings = SimpleNamespace(WATA_ENABLED=True)
    assert spec.is_visible(settings, {"wata_service": SimpleNamespace(configured=True)})
    assert not spec.is_visible(settings, {"wata_service": SimpleNamespace(configured=False)})
    assert not spec.is_visible(SimpleNamespace(WATA_ENABLED=False), {})


def test_common_sale_mode_helpers_cover_provider_payment_records():
    assert sale_mode_base("traffic_package@premium|anything") == "traffic_package"
    assert sale_mode_is_traffic("premium_topup@vip")
    assert sale_mode_is_hwid_devices("hwid_devices@vip")
    assert sale_mode_tariff_key("subscription@vip") == "vip"
    assert format_number_for_payload(10.0) == "10"
    assert format_number_for_payload(10.5) == "10.5"

    traffic = payment_record_amounts(months=20, traffic_gb=20.5, sale_mode="topup@vip")
    assert traffic.months == 20
    assert traffic.purchased_gb == 20.5
    assert traffic.purchased_hwid_devices is None
    assert traffic.tariff_key == "vip"
    assert traffic.traffic_sale

    hwid = payment_record_amounts(months=3, sale_mode="hwid_devices@vip")
    assert hwid.months == 3
    assert hwid.purchased_gb is None
    assert hwid.purchased_hwid_devices == 3
    assert hwid.tariff_key == "vip"
    assert hwid.hwid_devices_sale
