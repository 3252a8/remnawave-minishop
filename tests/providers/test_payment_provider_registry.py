import asyncio
import importlib
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.keyboards.inline.user_keyboards import get_payment_method_keyboard
from bot.payment_providers import (
    build_provider_configs,
    get_provider_spec,
    iter_provider_specs,
    iter_service_keys,
    pending_statuses,
    provider_admin_only_pairs,
    provider_emoji_map,
    provider_label_map,
    provider_supports_recurring,
    provider_telegram_button_text,
    recurring_provider_services,
    resolve_provider_presentation,
)
from bot.payment_providers.shared import (
    PaymentCallbackParts,
    format_number_for_payload,
    payment_record_amounts,
    payment_units_for_activation,
    quote_hwid_callback_parts,
    sale_mode_base,
    sale_mode_is_hwid_devices,
    sale_mode_is_traffic,
    sale_mode_tariff_key,
)
from bot.payment_providers.yookassa import (
    _parse_saved_list_payload,
    _resolve_yookassa_activation_amounts,
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
    "heleket": "HeleketService",
    "paykilla": "PaykillaService",
    "lava": "LavaService",
    "pally": "PallyService",
    "cloudpayments": "CloudPaymentsService",
    "stripe": "StripeService",
    "qa": "QaPaymentService",
}


def test_legacy_provider_integration_files_are_removed():
    repo_root = Path(__file__).resolve().parents[2]

    for relative_path in _LEGACY_PROVIDER_FILES:
        assert not (repo_root / relative_path).exists()


def test_every_provider_module_owns_its_service_and_spec():
    for module_name, service_class_name in _PROVIDER_MODULES.items():
        module = importlib.import_module(f"bot.payment_providers.{module_name}")

        assert hasattr(module, service_class_name)
        assert hasattr(module, "SPEC") or hasattr(module, "SPECS")


def test_wata_registers_card_and_crypto_specs_on_one_service():
    spec = get_provider_spec("wata")
    crypto_spec = get_provider_spec("wata_crypto")

    assert spec is not None
    assert crypto_spec is not None
    assert spec.service_key == "wata_service"
    assert crypto_spec.service_key == "wata_service"
    assert spec.pending_status == "pending_wata"
    assert crypto_spec.pending_status == "pending_wata"
    assert spec.callback_prefix == "pay_wata"
    assert crypto_spec.callback_prefix == "pay_wata_crypto"
    assert spec.router is not None
    assert spec.create_service is not None
    assert spec.webhook_route is not None
    assert spec.create_webapp_payment is not None
    assert crypto_spec.create_webapp_payment is not None


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
    assert spec.supports_recurring
    assert provider_supports_recurring("yookassa")


def test_recurring_provider_registry_includes_saved_method_providers():
    yookassa_service = SimpleNamespace()
    cloudpayments_service = SimpleNamespace()
    stripe_service = SimpleNamespace()
    services = {
        "yookassa_service": yookassa_service,
        "cloudpayments_service": cloudpayments_service,
        "stripe_service": stripe_service,
        "wata_service": SimpleNamespace(),
    }

    recurring = recurring_provider_services(services)

    assert recurring["yookassa"] is yookassa_service
    assert recurring["cloudpayments"] is cloudpayments_service
    assert recurring["stripe"] is stripe_service
    assert "wata" not in recurring
    assert provider_supports_recurring("cloudpayments")
    assert provider_supports_recurring("stripe")


def test_every_payment_method_has_registry_driven_webapp_creator():
    missing = [spec.id for spec in iter_provider_specs() if spec.create_webapp_payment is None]

    assert missing == []


def test_service_keys_and_statuses_come_from_provider_specs():
    assert set(iter_service_keys()) == {
        "yookassa_service",
        "freekassa_service",
        "platega_service",
        "severpay_service",
        "wata_service",
        "stars_service",
        "bepusdt_service",
        "cryptopay_service",
        "epay_service",
        "heleket_service",
        "paykilla_service",
        "lava_service",
        "pally_service",
        "cloudpayments_service",
        "stripe_service",
        "qa_service",
    }
    assert set(pending_statuses()) >= {
        "pending",
        "pending_yookassa",
        "pending_freekassa",
        "pending_platega",
        "pending_severpay",
        "pending_wata",
        "pending_bepusdt",
        "pending_cryptopay",
        "pending_epay",
        "pending_stars",
        "pending_heleket",
        "pending_paykilla",
        "pending_lava",
        "pending_pally",
        "pending_cloudpayments",
        "pending_stripe",
        "pending_qa",
    }


def test_qa_provider_is_runtime_gated(monkeypatch):
    from bot.payment_providers.qa import QaPaymentConfig, QaPaymentService

    monkeypatch.setenv("QA_PAYMENT_ENABLED", "True")
    monkeypatch.setenv("QA_PAYMENT_SECRET", "qa-secret")
    config = QaPaymentConfig()

    common = {
        "bot": SimpleNamespace(),
        "async_session_factory": SimpleNamespace(),
        "i18n": SimpleNamespace(),
        "subscription_service": SimpleNamespace(),
        "referral_service": SimpleNamespace(),
        "config": config,
    }

    production = QaPaymentService(
        settings=SimpleNamespace(APP_RUNTIME_MODE="production"),
        **common,
    )
    development = QaPaymentService(
        settings=SimpleNamespace(APP_RUNTIME_MODE="development"),
        **common,
    )

    assert not production.configured
    assert development.configured

    monkeypatch.setenv("QA_PAYMENT_ENABLED", "False")
    monkeypatch.delenv("QA_PAYMENT_SECRET", raising=False)


def test_provider_labels_and_emojis_include_storage_keys_and_method_aliases():
    labels = provider_label_map()
    emojis = provider_emoji_map()

    assert labels["wata"] == "Wata"
    assert labels["wata_crypto"] == "Wata"
    assert labels["telegram_stars"] == "Telegram Stars"
    assert labels["stars"] == "Telegram Stars"
    assert labels["platega"] == "Platega"
    assert labels["platega_sbp"] == "Platega"
    assert labels["platega_crypto"] == "Platega"
    assert emojis["stars"] == get_provider_spec("stars").default_telegram_emoji
    assert emojis["telegram_stars"] == get_provider_spec("stars").default_telegram_emoji
    assert emojis["cryptopay"] == get_provider_spec("cryptopay").default_telegram_emoji
    assert labels["paykilla"] == "PayKilla"
    assert labels["pally"] == "Pally"
    assert labels["qa"] == "QA Payment"


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

    assert (
        provider_telegram_button_text(spec, SimpleNamespace(), language="en")
        == f"{spec.default_telegram_emoji} Wata"
    )

    settings = SimpleNamespace(PAYMENT_WATA_TELEGRAM_LABEL_EN="Pay Wata")
    assert (
        provider_telegram_button_text(spec, settings, language="en")
        == f"{spec.default_telegram_emoji} Pay Wata"
    )


def test_provider_presentation_ignores_cross_language_override():
    spec = get_provider_spec("yookassa")
    assert spec is not None

    settings = SimpleNamespace(PAYMENT_YOOKASSA_WEBAPP_LABEL_RU="Карта")

    assert resolve_provider_presentation(spec, settings, language="en").webapp_label == "YooKassa"


def test_subscription_hwid_renewal_token_adds_quote_to_callback_parts():
    service = SimpleNamespace(
        quote_hwid_device_renewal_for_subscription=AsyncMock(
            return_value={
                "device_count": 2,
                "price": 50,
                "valid_from": "2099-02-01",
                "valid_until": "2099-03-01",
            }
        )
    )
    session = AsyncMock()

    parts, quote = asyncio.run(
        quote_hwid_callback_parts(
            session=session,
            user_id=77,
            parts=PaymentCallbackParts(
                months=1,
                price=100,
                sale_mode="subscription@basic|hwid_renewal",
            ),
            subscription_service=service,
            currency="rub",
        )
    )

    assert parts is not None
    assert quote is not None
    assert parts.months == 1
    assert parts.price == 150
    assert quote["device_count"] == 2
    service.quote_hwid_device_renewal_for_subscription.assert_awaited_once_with(
        session,
        user_id=77,
        target_tariff_key="basic",
        months=1,
        currency="rub",
    )


def test_payment_method_keyboard_uses_custom_telegram_text_without_changing_callback(monkeypatch):
    monkeypatch.setenv("WATA_ENABLED", "True")
    monkeypatch.setenv("WATA_API_TOKEN", "wata-token")
    monkeypatch.setenv("PAYMENT_WATA_TELEGRAM_LABEL_EN", "Wata custom")
    monkeypatch.setenv("PAYMENT_WATA_TELEGRAM_EMOJI", "💸")
    build_provider_configs(force=True)

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="wata",
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


def test_payment_method_keyboard_filters_providers_by_payment_currency(monkeypatch):
    monkeypatch.setenv("YOOKASSA_ENABLED", "True")
    monkeypatch.setenv("WATA_ENABLED", "True")
    monkeypatch.setenv("WATA_API_TOKEN", "wata-token")
    build_provider_configs(force=True)

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="yookassa,wata",
    )
    i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)

    markup = get_payment_method_keyboard(
        months=1,
        price=10,
        stars_price=None,
        currency_symbol_val="USD",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
    )

    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "pay_wata:1:10:subscription" in callbacks
    assert all(not callback.startswith("pay_yk:") for callback in callbacks)


def test_payment_method_keyboard_uses_payment_currency_for_symbol_labels(monkeypatch):
    monkeypatch.setenv("PLATEGA_ENABLED", "True")
    monkeypatch.setenv("PLATEGA_SBP_ENABLED", "True")
    monkeypatch.setenv("PLATEGA_MERCHANT_ID", "merchant")
    monkeypatch.setenv("PLATEGA_SECRET", "secret")
    monkeypatch.setenv("YOOKASSA_ENABLED", "True")
    monkeypatch.setenv("YOOKASSA_SHOP_ID", "shop")
    monkeypatch.setenv("YOOKASSA_SECRET_KEY", "secret")
    monkeypatch.setenv("WATA_ENABLED", "True")
    monkeypatch.setenv("WATA_API_TOKEN", "wata-token")
    build_provider_configs(force=True)

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        DEFAULT_CURRENCY_SYMBOL="\u20bd",
        PAYMENT_METHODS_ORDER="platega_sbp,yookassa,wata",
        STARS_ENABLED=False,
    )
    i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)

    markup = get_payment_method_keyboard(
        months=1,
        price=150,
        stars_price=None,
        currency_symbol_val="\u20bd",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
    )

    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "pay_platega_sbp:1:150:subscription" in callbacks
    assert "pay_yk:1:150:subscription" in callbacks
    assert "pay_wata:1:150:subscription" in callbacks


def test_payment_method_keyboard_filters_paykilla_by_converted_minimum(monkeypatch):
    from bot.payment_providers.paykilla import config as paykilla_core

    monkeypatch.setenv("PAYKILLA_ENABLED", "True")
    monkeypatch.setenv("PAYKILLA_API_KEY", "paykilla-public")
    monkeypatch.setenv("PAYKILLA_SECRET_KEY", "paykilla-secret")
    monkeypatch.setenv("PAYKILLA_MIN_PAYMENT_AMOUNT", "10")
    monkeypatch.setenv("PAYKILLA_MIN_PAYMENT_CURRENCY", "USD")
    build_provider_configs(force=True)
    monkeypatch.setattr(
        paykilla_core,
        "_exchange_rate_sync",
        lambda _config, _source, _target: Decimal("0.013586"),
    )

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="paykilla",
        STARS_ENABLED=False,
    )
    i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)

    below_minimum = get_payment_method_keyboard(
        months=1,
        price=190,
        stars_price=None,
        currency_symbol_val="RUB",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
    )
    above_minimum = get_payment_method_keyboard(
        months=1,
        price=1000,
        stars_price=None,
        currency_symbol_val="RUB",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
    )

    below_callbacks = [
        button.callback_data
        for row in below_minimum.inline_keyboard
        for button in row
        if button.callback_data
    ]
    above_callbacks = [
        button.callback_data
        for row in above_minimum.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert all(not callback.startswith("pay_paykilla:") for callback in below_callbacks)
    assert "pay_paykilla:1:1000:subscription" in above_callbacks


def test_admin_only_provider_is_visible_only_to_admins(monkeypatch):
    from bot.app.web.webapp.serializers import _serialize_payment_methods

    monkeypatch.setenv("WATA_ENABLED", "False")
    monkeypatch.setenv("WATA_ADMIN_ONLY_ENABLED", "True")
    monkeypatch.setenv("WATA_API_TOKEN", "wata-token")
    build_provider_configs(force=True)

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="wata",
        DEFAULT_CURRENCY_SYMBOL="RUB",
        ADMIN_IDS="42",
        STARS_ENABLED=False,
    )
    i18n = SimpleNamespace(gettext=lambda _lang, key, **_kwargs: key)
    app = {"wata_service": SimpleNamespace(configured=True)}
    spec = get_provider_spec("wata")

    regular_markup = get_payment_method_keyboard(
        months=1,
        price=150,
        stars_price=None,
        currency_symbol_val="RUB",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
        user_id=7,
    )
    admin_markup = get_payment_method_keyboard(
        months=1,
        price=150,
        stars_price=None,
        currency_symbol_val="RUB",
        lang="en",
        i18n_instance=i18n,
        settings=settings,
        user_id=42,
    )

    assert spec is not None
    assert not spec.is_visible(settings, app)
    assert not spec.is_visible_for_user(settings, app, is_admin=False)
    assert spec.is_visible_for_user(settings, app, is_admin=True)
    assert all(
        not button.callback_data.startswith("pay_wata:")
        for row in regular_markup.inline_keyboard
        for button in row
    )
    assert admin_markup.inline_keyboard[0][0].callback_data == "pay_wata:1:150:subscription"
    assert _serialize_payment_methods(settings, app, "en", is_admin=False) == []
    assert _serialize_payment_methods(settings, app, "en", is_admin=True)[0]["id"] == "wata"


def test_webapp_payment_methods_filter_by_default_currency(monkeypatch):
    from bot.app.web.webapp.serializers import _serialize_payment_methods

    monkeypatch.setenv("YOOKASSA_ENABLED", "True")
    monkeypatch.setenv("WATA_ENABLED", "True")
    monkeypatch.setenv("WATA_API_TOKEN", "wata-token")
    build_provider_configs(force=True)

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="yookassa,wata",
        DEFAULT_CURRENCY_SYMBOL="USD",
        STARS_ENABLED=False,
    )
    app = {
        "yookassa_service": SimpleNamespace(configured=True),
        "wata_service": SimpleNamespace(configured=True),
    }

    methods = _serialize_payment_methods(settings, app, "en", is_admin=False)

    assert [method["id"] for method in methods] == ["wata"]


def test_webapp_payment_methods_include_paykilla_minimum_metadata(monkeypatch):
    from bot.app.web.webapp.serializers import _serialize_payment_methods
    from bot.payment_providers.paykilla import config as paykilla_core

    monkeypatch.setenv("PAYKILLA_ENABLED", "True")
    monkeypatch.setenv("PAYKILLA_API_KEY", "paykilla-public")
    monkeypatch.setenv("PAYKILLA_SECRET_KEY", "paykilla-secret")
    monkeypatch.setenv("PAYKILLA_MIN_PAYMENT_AMOUNT", "10")
    monkeypatch.setenv("PAYKILLA_MIN_PAYMENT_CURRENCY", "USD")
    build_provider_configs(force=True)
    monkeypatch.setattr(
        paykilla_core,
        "_exchange_rate_sync",
        lambda _config, _source, _target: Decimal("0.013586"),
    )

    settings = Settings(
        _env_file=None,
        BOT_TOKEN="token",
        POSTGRES_USER="app_user",
        POSTGRES_PASSWORD="app_password",
        TARIFFS_CONFIG_PATH="missing-tariffs.json",
        PAYMENT_METHODS_ORDER="paykilla",
        DEFAULT_CURRENCY_SYMBOL="RUB",
        STARS_ENABLED=False,
    )
    app = {"paykilla_service": SimpleNamespace(configured=True)}

    methods = _serialize_payment_methods(settings, app, "en", is_admin=False)

    assert methods == [
        {
            "id": "paykilla",
            "name": "PayKilla",
            "icon": "Bitcoin",
            "min_amount": "736.06",
            "min_currency": "RUB",
            "configured_min_amount": "10.00",
            "configured_min_currency": "USD",
        }
    ]


def test_admin_only_provider_toggle_pairs_are_declared():
    pairs = set(provider_admin_only_pairs())

    assert ("WATA_ENABLED", "WATA_ADMIN_ONLY_ENABLED") in pairs
    assert ("WATA_CRYPTO_ENABLED", "WATA_CRYPTO_ADMIN_ONLY_ENABLED") in pairs
    assert ("PLATEGA_SBP_ENABLED", "PLATEGA_SBP_ADMIN_ONLY_ENABLED") in pairs
    assert ("PLATEGA_CRYPTO_ENABLED", "PLATEGA_CRYPTO_ADMIN_ONLY_ENABLED") in pairs
    assert ("STARS_ENABLED", "STARS_ADMIN_ONLY_ENABLED") in pairs


def test_admin_only_provider_toggle_normalization_disables_public_pair():
    from bot.services.settings_override_service import _normalize_exclusive_provider_toggles

    updates, deletes = _normalize_exclusive_provider_toggles(
        {"WATA_ADMIN_ONLY_ENABLED": True},
        ["WATA_ENABLED"],
    )

    assert updates["WATA_ADMIN_ONLY_ENABLED"] is True
    assert updates["WATA_ENABLED"] is False
    assert deletes == []


def test_provider_callbacks_are_built_from_specs():
    wata = get_provider_spec("wata")
    wata_crypto = get_provider_spec("wata_crypto")
    stars = get_provider_spec("stars")

    assert wata is not None
    assert wata_crypto is not None
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
        wata_crypto.callback_data(
            value="1",
            rub_price=150,
            stars_price=None,
            sale_mode="subscription",
        )
        == "pay_wata_crypto:1:150:subscription"
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
    assert (
        stars.callback_data(
            value="1",
            rub_price=150,
            stars_price=None,
            sale_mode="subscription",
        )
        is None
    )


def test_provider_visibility_uses_service_configuration(monkeypatch):
    monkeypatch.setenv("WATA_ENABLED", "True")
    monkeypatch.setenv("WATA_API_TOKEN", "wata-token")
    monkeypatch.delenv("WATA_ADMIN_ONLY_ENABLED", raising=False)
    build_provider_configs(force=True)

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
    assert sale_mode_tariff_key("subscription@vip|bot") == "vip"
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

    payment = SimpleNamespace(
        purchased_gb=None,
        purchased_hwid_devices=3,
        subscription_duration_months=None,
    )
    assert payment_units_for_activation(payment, "hwid_devices@vip") == 3


def test_yookassa_hwid_webapp_metadata_uses_device_count_for_activation():
    (
        subscription_months,
        traffic_amount_gb,
        hwid_devices_count,
        months_for_activation,
        traffic_gb_for_activation,
    ) = _resolve_yookassa_activation_amounts(
        sale_mode_base="hwid_devices",
        subscription_months_raw="0",
        traffic_gb_raw=None,
        hwid_devices_raw="3",
    )

    assert subscription_months == 0
    assert traffic_amount_gb == 0
    assert hwid_devices_count == 3
    assert months_for_activation == 3
    assert traffic_gb_for_activation is None


def test_hwid_callback_quote_rejects_fractional_device_count():
    subscription_service = SimpleNamespace(quote_hwid_device_topup=AsyncMock())

    quoted_parts, quote = asyncio.run(
        quote_hwid_callback_parts(
            session=AsyncMock(),
            user_id=42,
            parts=PaymentCallbackParts(
                months=1.9,
                price=50,
                sale_mode="hwid_devices@vip",
            ),
            subscription_service=subscription_service,
        )
    )

    assert quoted_parts is None
    assert quote is None
    subscription_service.quote_hwid_device_topup.assert_not_awaited()


def test_yookassa_hwid_metadata_rejects_fractional_device_count():
    with pytest.raises(ValueError):
        _resolve_yookassa_activation_amounts(
            sale_mode_base="hwid_devices",
            subscription_months_raw="0",
            traffic_gb_raw=None,
            hwid_devices_raw="1.9",
        )


def test_yookassa_saved_card_payload_parser_accepts_new_and_legacy_formats():
    assert _parse_saved_list_payload("1:100:0:subscription@vip|hwid_renewal") == (
        1,
        100,
        0,
        "subscription@vip|hwid_renewal",
    )
    assert _parse_saved_list_payload("1:100:subscription@vip|hwid_renewal") == (
        1,
        100,
        0,
        "subscription@vip|hwid_renewal",
    )
    assert _parse_saved_list_payload("bad:100:subscription") is None
