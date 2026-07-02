from collections import defaultdict
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from scripts.import_legacy import (
    RemnashopImporter,
    _extract_panel_subscription_uuid,
    parse_remnashop_env_text,
    remnashop_build_tariff_catalog,
    remnashop_env_overrides,
    remnashop_months_from_plan_snapshot,
    remnashop_notification_overrides,
    remnashop_payment_gateway_overrides,
    remnashop_post_migration_actions,
    remnashop_pricing_amount,
    remnashop_pricing_currency,
    remnashop_row_telegram_id,
    remnashop_sale_mode,
    remnashop_subscription_provider,
    remnashop_traffic_gb_to_bytes,
    remnashop_transaction_status,
)


def test_remnashop_existing_user_profile_is_preserved_on_merge():
    importer = RemnashopImporter.__new__(RemnashopImporter)
    importer.on_conflict = "merge"
    importer.summary = {"users": defaultdict(int)}
    user = SimpleNamespace(
        username="current_admin",
        first_name="Current",
        last_name="Admin",
        language_code="ru",
    )

    importer._merge_existing_user_profile(
        user,
        username="legacy_admin",
        first_name="Legacy",
        last_name="Name",
        language="en",
    )

    assert user.username == "current_admin"
    assert user.first_name == "Current"
    assert user.last_name == "Admin"
    assert user.language_code == "ru"
    assert importer.summary["users"]["profile_preserved"] == 1


def test_remnashop_existing_user_profile_can_be_overwritten_explicitly():
    importer = RemnashopImporter.__new__(RemnashopImporter)
    importer.on_conflict = "overwrite"
    importer.summary = {"users": defaultdict(int)}
    user = SimpleNamespace(
        username="current_admin",
        first_name="Current",
        last_name="Admin",
        language_code="ru",
    )

    importer._merge_existing_user_profile(
        user,
        username="legacy_admin",
        first_name="Legacy",
        last_name="Name",
        language="en",
    )

    assert user.username == "legacy_admin"
    assert user.first_name == "Legacy"
    assert user.last_name == "Name"
    assert user.language_code == "en"


def test_remnashop_promocode_subscription_reward_reads_plan_snapshot():
    importer = RemnashopImporter.__new__(RemnashopImporter)

    assert (
        importer._promo_bonus_days(
            {
                "reward_type": "SUBSCRIPTION",
                "reward": None,
                "plan_snapshot": {"duration_days": 45},
            }
        )
        == 45
    )


def test_remnashop_pricing_helpers_read_final_amount_and_currency():
    pricing = {"final_amount": "199.50", "currency": "rub"}

    assert remnashop_pricing_amount(pricing) == 199.5
    assert remnashop_pricing_currency(pricing) == "RUB"


def test_remnashop_traffic_limit_is_converted_from_gib():
    assert remnashop_traffic_gb_to_bytes(10) == 10 * 1024**3
    assert remnashop_traffic_gb_to_bytes(None) is None


def test_remnashop_status_and_sale_mode_mapping_matches_current_payment_model():
    assert remnashop_transaction_status("COMPLETED", "YOOKASSA") == "succeeded"
    assert remnashop_transaction_status("PENDING", "WATA") == "pending_wata"
    assert remnashop_transaction_status("CANCELED", "WATA") == "canceled"
    assert remnashop_sale_mode("NEW") == "subscription"
    assert remnashop_sale_mode("NEW", {"type": "TRAFFIC"}) == "traffic_package"
    assert remnashop_sale_mode("NEW", {"type": "DEVICES"}) == "hwid_devices"
    assert remnashop_sale_mode("RENEW") == "subscription"
    assert remnashop_sale_mode("CHANGE") == "tariff_upgrade"


def test_remnashop_subscription_provider_parses_string_booleans():
    for value in (False, 0, "0", "false", "False", "off", "", None):
        assert remnashop_subscription_provider(value) == "remnashop"

    for value in (True, 1, "1", "true", "yes", "on"):
        assert remnashop_subscription_provider(value) == "trial"


def test_remnashop_plan_months_prefers_snapshot_then_dates():
    assert remnashop_months_from_plan_snapshot({"duration_days": 90}) == 3
    assert remnashop_months_from_plan_snapshot({"months": 12}) == 12
    assert (
        remnashop_months_from_plan_snapshot(
            {},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            expire_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
        == 3
    )


def test_remnashop_env_parser_and_overrides_map_safe_values():
    env = parse_remnashop_env_text(
        """
        # old Remnashop
        export REMNAWAVE_HOST=panel.example.com
        REMNAWAVE_TOKEN='panel-token#kept'
        REMNAWAVE_COOKIE="rw_session=session-value"
        REMNAWAVE_WEBHOOK_SECRET="panel secret"
        BOT_SUPPORT_USERNAME=@support_bot # comment
        APP_DEFAULT_LOCALE=en
        BOT_MINI_APP=https://app.example.com/
        APP_DOMAIN=old.example.com
        """
    )

    assert env["REMNAWAVE_TOKEN"] == "panel-token#kept"
    assert env["BOT_SUPPORT_USERNAME"] == "@support_bot"

    overrides = remnashop_env_overrides(env)
    assert overrides == {
        "PANEL_API_URL": "https://panel.example.com/api",
        "PANEL_API_KEY": "panel-token#kept",
        "PANEL_API_COOKIE": "rw_session=session-value",
        "PANEL_WEBHOOK_SECRET": "panel secret",
        "SUPPORT_LINK": "https://t.me/support_bot",
        "DEFAULT_LANGUAGE": "en",
    }


def test_remnashop_env_overrides_skip_placeholders_and_mini_app():
    overrides = remnashop_env_overrides(
        {
            "REMNAWAVE_HOST": "change_me",
            "REMNAWAVE_TOKEN": "change_me",
            "REMNAWAVE_WEBHOOK_SECRET": "change_me",
            "BOT_SUPPORT_USERNAME": "change_me",
            "APP_DEFAULT_LOCALE": "change_me",
            "BOT_MINI_APP": "https://old-mini-app.example.com/",
        }
    )

    assert overrides == {}


def test_remnashop_notification_routes_map_to_log_chat_settings():
    result = remnashop_notification_overrides(
        {
            "enabled": True,
            "routes": {
                "SUBSCRIPTION": {"chat_id": -111, "thread_id": None},
                "SYSTEM": {"chat_id": -5588668915, "thread_id": 42},
            },
        }
    )

    assert result["overrides"] == {"LOG_CHAT_ID": -5588668915, "LOG_THREAD_ID": 42}
    assert result["route"]["route"] == "SYSTEM"


def test_remnashop_tariff_catalog_is_generated_from_plans_durations_and_prices():
    plans = [
        {
            "id": 3,
            "order_index": 1,
            "is_active": True,
            "type": "BOTH",
            "availability": "ALL",
            "name": "Pro 300ГБ",
            "tag": "PRO",
            "traffic_limit": 300,
            "device_limit": 6,
            "internal_squads": ["squad-1"],
        },
        {
            "id": 8,
            "order_index": 2,
            "is_active": True,
            "type": "TRAFFIC",
            "availability": "ALL",
            "name": "Трафик 50ГБ",
            "tag": "TRAFFIC50",
            "traffic_limit": 50,
            "device_limit": 0,
            "internal_squads": ["squad-1"],
            "public_code": "traffic50gb",
        },
    ]
    durations = [
        {"id": 4, "plan_id": 3, "days": 30, "order_index": 1},
        {"id": 5, "plan_id": 3, "days": 180, "order_index": 2},
        {"id": 13, "plan_id": 8, "days": 30, "order_index": 1},
    ]
    prices = [
        {"plan_duration_id": 4, "currency": "RUB", "price": 599},
        {"plan_duration_id": 4, "currency": "XTR", "price": 299},
        {"plan_duration_id": 5, "currency": "RUB", "price": 2990},
        {"plan_duration_id": 13, "currency": "RUB", "price": 249},
        {"plan_duration_id": 13, "currency": "USD", "price": 2.5},
        {"plan_duration_id": 13, "currency": "XTR", "price": 125},
    ]

    result = remnashop_build_tariff_catalog(
        plans,
        durations,
        prices,
        default_currency="RUB",
    )

    assert result["warnings"] == []
    assert result["tariff_map"]["3"] == "pro"
    assert result["tariff_map"]["TRAFFIC50"] == "traffic50"
    catalog = result["catalog"]
    assert catalog["default_tariff"] == "pro"
    pro, traffic = catalog["tariffs"]
    assert pro["names"]["ru"] == "Pro 300ГБ"
    assert pro["billing_model"] == "period"
    assert pro["monthly_gb"] == 300
    assert pro["prices"]["rub"] == {"1": 599.0, "6": 2990.0}
    assert pro["prices"]["stars"] == {"1": 299.0}
    assert traffic["names"]["ru"] == "Трафик 50ГБ"
    assert traffic["billing_model"] == "traffic"
    assert traffic["hwid_device_limit"] == 0
    assert traffic["traffic_packages"]["rub"] == [{"gb": 50.0, "price": 249.0}]
    assert traffic["traffic_packages"]["usd"] == [{"gb": 50.0, "price": 2.5}]
    assert traffic["traffic_packages"]["stars"] == [{"gb": 50.0, "price": 125.0}]


def test_remnashop_row_telegram_id_supports_fk_only_schema():
    user_map = {1: 504250615, 2: 7410865527}

    assert remnashop_row_telegram_id({"user_telegram_id": 123}, user_map) == 123
    assert remnashop_row_telegram_id({"user_id": 2}, user_map) == 7410865527
    assert (
        remnashop_row_telegram_id(
            {"referrer_id": 1},
            user_map,
            user_id_key="referrer_id",
            telegram_id_key="referrer_telegram_id",
        )
        == 504250615
    )
    assert remnashop_row_telegram_id({"user_id": 3}, user_map) is None


def test_remnashop_subscription_url_token_is_kept_as_panel_subscription_uuid():
    assert (
        _extract_panel_subscription_uuid(
            "https://testsub.example/DqrawmRnhfooy_P0",
            "31a77a97-5730-46bf-bf8c-944feb0d6cd7",
        )
        == "DqrawmRnhfooy_P0"
    )
    assert (
        _extract_panel_subscription_uuid(
            "https://testsub.example/u/6e8bee84-cf50-4a08-92df-c85ac8904e44",
            "31a77a97-5730-46bf-bf8c-944feb0d6cd7",
        )
        == "6e8bee84-cf50-4a08-92df-c85ac8904e44"
    )


def test_remnashop_yookassa_gateway_maps_to_current_provider_settings():
    result = remnashop_payment_gateway_overrides(
        {
            "type": "YOOKASSA",
            "currency": "RUB",
            "is_active": True,
            "settings": {
                "shop_id": "shop-1",
                "api_key": "secret",
                "customer": "receipt@example.com",
                "vat_code": 1,
            },
        }
    )

    assert result["supported"] is True
    assert result["provider_ids"] == ["yookassa"]
    assert result["overrides"] == {
        "YOOKASSA_ENABLED": True,
        "YOOKASSA_SHOP_ID": "shop-1",
        "YOOKASSA_SECRET_KEY": "secret",
        "YOOKASSA_DEFAULT_RECEIPT_EMAIL": "receipt@example.com",
        "YOOKASSA_VAT_CODE": 1,
    }


def test_remnashop_free_kassa_and_platega_gateways_map_available_settings():
    freekassa = remnashop_payment_gateway_overrides(
        {
            "type": "FREEKASSA",
            "is_active": True,
            "settings": {
                "shop_id": "merchant",
                "api_key": "api",
                "secret_word_2": "notify-secret",
                "payment_system_id": 42,
                "customer_ip": "203.0.113.10",
                "customer_email": "payer@example.com",
            },
        }
    )
    assert freekassa["provider_ids"] == ["freekassa"]
    assert freekassa["overrides"]["FREEKASSA_SECOND_SECRET"] == "notify-secret"
    assert freekassa["overrides"]["FREEKASSA_PAYMENT_METHOD_ID"] == 42
    assert any("customer_email" in warning for warning in freekassa["warnings"])

    platega = remnashop_payment_gateway_overrides(
        {
            "type": "PLATEGA",
            "currency": "RUB",
            "is_active": True,
            "settings": {
                "merchant_id": "merchant",
                "api_key": "secret",
                "payment_method": 2,
            },
        }
    )
    assert platega["provider_ids"] == ["platega_sbp"]
    assert platega["overrides"]["PLATEGA_SBP_ENABLED"] is True
    assert platega["overrides"]["PLATEGA_SBP_METHOD"] == 2
    assert "PLATEGA_SUPPORTED_CURRENCIES" not in platega["overrides"]


def test_remnashop_crypto_provider_currency_is_not_imported_as_setting_override():
    cryptopay = remnashop_payment_gateway_overrides(
        {
            "type": "CRYPTOPAY",
            "currency": "USD",
            "is_active": True,
            "settings": {"api_key": "crypto-token"},
        }
    )
    assert cryptopay["overrides"] == {
        "CRYPTOPAY_ENABLED": True,
        "CRYPTOPAY_TOKEN": "crypto-token",
    }
    assert any("указана валюта USD" in warning for warning in cryptopay["warnings"])

    heleket = remnashop_payment_gateway_overrides(
        {
            "type": "HELEKET",
            "currency": "USD",
            "is_active": True,
            "settings": {"merchant_id": "merchant", "api_key": "secret"},
        }
    )
    assert heleket["overrides"] == {
        "HELEKET_ENABLED": True,
        "HELEKET_MERCHANT_ID": "merchant",
        "HELEKET_API_KEY": "secret",
    }
    assert "HELEKET_CURRENCY" not in heleket["overrides"]

    paykilla = remnashop_payment_gateway_overrides(
        {
            "type": "PAYKILLA",
            "currency": "USD",
            "is_active": True,
            "settings": {"public_key": "public", "secret_key": "secret"},
        }
    )
    assert paykilla["overrides"] == {
        "PAYKILLA_ENABLED": True,
        "PAYKILLA_API_KEY": "public",
        "PAYKILLA_SECRET_KEY": "secret",
    }
    assert "PAYKILLA_CURRENCY" not in paykilla["overrides"]
    assert any("указана валюта USD" in warning for warning in paykilla["warnings"])


def test_remnashop_unsupported_gateway_is_reported_without_overrides():
    result = remnashop_payment_gateway_overrides(
        {
            "type": "ROBOKASSA",
            "is_active": True,
            "settings": {"merchant_login": "shop"},
        }
    )

    assert result["supported"] is False
    assert result["provider_ids"] == []
    assert result["overrides"] == {}


def test_remnashop_encrypted_gateway_settings_need_app_crypt_key():
    result = remnashop_payment_gateway_overrides(
        {
            "type": "WATA",
            "is_active": True,
            "settings": {"api_key": "enc_not-a-fernet-token"},
        }
    )

    assert result["overrides"] == {"WATA_ENABLED": True}
    assert any("APP_CRYPT_KEY" in warning for warning in result["warnings"])


def test_remnashop_encrypted_gateway_settings_decrypt_with_app_crypt_key():
    cryptography = pytest.importorskip(
        "cryptography.fernet",
        reason="encrypted legacy gateway fixtures require cryptography",
    )
    key = cryptography.Fernet.generate_key().decode()
    token = cryptography.Fernet(key.encode()).encrypt(b"wata-token").decode()

    result = remnashop_payment_gateway_overrides(
        {
            "type": "WATA",
            "is_active": True,
            "settings": {"api_key": f"enc_{token}"},
        },
        crypt_key=key,
    )

    assert result["overrides"] == {
        "WATA_ENABLED": True,
        "WATA_API_TOKEN": "wata-token",
    }
    assert result["warnings"] == []


def test_remnashop_post_migration_actions_include_new_webhook_urls():
    actions = remnashop_post_migration_actions(
        target_webhook_base_url="https://webhooks.example.com/",
        imported_provider_ids=["yookassa", "wata", "yookassa"],
        source_env={"APP_DOMAIN": "old.example.com"},
    )

    assert actions["remnawave_panel"]["new_url"] == "https://webhooks.example.com/webhook/panel"
    assert actions["telegram"]["new_url"] == "https://webhooks.example.com/tg/webhook"
    assert actions["source_urls"]["payments"] == "https://old.example.com/api/v1/payments/<gateway>"
    assert actions["payment_providers"] == [
        {
            "provider": "yookassa",
            "new_url": "https://webhooks.example.com/webhook/yookassa",
            "where": "YooKassa merchant cabinet -> HTTP notifications URL",
        },
        {
            "provider": "wata",
            "new_url": "https://webhooks.example.com/webhook/wata",
            "where": "WATA merchant dashboard -> webhook/callback URL",
        },
    ]
