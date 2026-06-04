from datetime import datetime, timezone

import pytest
from scripts.import_legacy import (
    parse_remnashop_env_text,
    remnashop_env_overrides,
    remnashop_months_from_plan_snapshot,
    remnashop_payment_gateway_overrides,
    remnashop_post_migration_actions,
    remnashop_pricing_amount,
    remnashop_pricing_currency,
    remnashop_sale_mode,
    remnashop_traffic_gb_to_bytes,
    remnashop_transaction_status,
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
    assert remnashop_sale_mode("RENEW") == "subscription"
    assert remnashop_sale_mode("CHANGE") == "tariff_upgrade"


def test_remnashop_plan_months_prefers_snapshot_then_dates():
    assert remnashop_months_from_plan_snapshot({"duration_days": 90}) == 3
    assert remnashop_months_from_plan_snapshot({"months": 12}) == 12
    assert (
        remnashop_months_from_plan_snapshot(
            {},
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expire_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        == 3
    )


def test_remnashop_env_parser_and_overrides_map_safe_values():
    env = parse_remnashop_env_text(
        """
        # old Remnashop
        export REMNAWAVE_HOST=panel.example.com
        REMNAWAVE_TOKEN='panel-token#kept'
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
    assert any("source currency was USD" in warning for warning in cryptopay["warnings"])

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
    assert any("source currency was USD" in warning for warning in paykilla["warnings"])


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
    cryptography = pytest.importorskip("cryptography.fernet")
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
