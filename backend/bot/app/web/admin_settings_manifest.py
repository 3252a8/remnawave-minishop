"""Manifest of settings editable from the admin web app.

Each entry describes a single overridable attribute on the global
``Settings`` instance. The manifest is the only contract between the
admin UI and the backend: keys not listed here cannot be changed via
the API, even by an admin.
"""

from __future__ import annotations

import re
from typing import Any

from bot.app.web.admin_settings_manifest_fields import SETTINGS_MANIFEST, SettingField
from config.support_links import normalize_support_link


def _provider_field_to_setting_field(spec: Any, manifest_field: Any) -> SettingField:
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
        i18n_label_key=getattr(manifest_field, "i18n_label_key", None),
        i18n_description_key=getattr(manifest_field, "i18n_description_key", None),
        i18n_subsection_key=getattr(manifest_field, "i18n_subsection_key", None),
    )


def aggregated_manifest() -> list[SettingField]:
    """SETTINGS_MANIFEST + per-provider fragments declared in provider SPECs."""
    from bot.payment_providers import iter_provider_manifest_fields  # local to avoid cycle

    fields: list[SettingField] = list(SETTINGS_MANIFEST)
    for spec, manifest_field in iter_provider_manifest_fields():
        fields.append(_provider_field_to_setting_field(spec, manifest_field))
    return fields


def get_field_by_key(key: str) -> SettingField | None:
    for field in aggregated_manifest():
        if field.key == key:
            return field
    return None


def manifest_keys() -> list[str]:
    return [f.key for f in aggregated_manifest()]


def coerce_value(field: SettingField, raw: Any) -> Any:
    """Coerce a value coming from JSON to the type declared by the field."""

    if field.type == "json":
        if raw is None:
            return ""
        text = raw if isinstance(raw, str) else str(raw)
        text = text.strip()
        if not text:
            return ""
        from config.subscription_guides_config import validate_subscription_guides_config_text

        validate_subscription_guides_config_text(text)
        return text

    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if not field.optional:
            raise ValueError(f"{field.key}: value required")
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
            float_value = float(str(raw).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field.key}: number expected") from exc
        if field.min is not None and float_value < field.min:
            raise ValueError(f"{field.key}: must be >= {field.min:g}")
        if field.max is not None and float_value > field.max:
            raise ValueError(f"{field.key}: must be <= {field.max:g}")
        return float_value

    if field.key == "SUPPORT_LINK":
        normalized = normalize_support_link(raw)
        if normalized is None:
            raise ValueError(
                "SUPPORT_LINK must be an HTTP(S) URL, @username, or t.me/username link"
            )
        return normalized

    if isinstance(raw, str):
        return raw.strip()
    return str(raw)


def _i18n_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "default"


# Shared provider option keys are intentionally allowlisted. Falling back to a
# slug for every English label makes one-off provider details look reusable even
# when the text still contains PayKilla/Wata/etc. specifics.
_PROVIDER_OPTION_LABEL_KEYS: dict[str, str] = {
    "Enabled": "admin_settings_provider_opt_enabled_label",
    "Merchant ID": "admin_settings_provider_opt_merchant_id_label",
    "First secret": "admin_settings_provider_opt_first_secret_label",
    "Second secret": "admin_settings_provider_opt_second_secret_label",
    "API key": "admin_settings_provider_opt_api_key_label",
    "Payment URL": "admin_settings_provider_opt_payment_url_label",
    "Payment method ID": "admin_settings_provider_opt_payment_method_id_label",
    "Server IP": "admin_settings_provider_opt_server_ip_label",
    "Trusted IPs": "admin_settings_provider_opt_trusted_ips_label",
    "Base URL": "admin_settings_provider_opt_base_url_label",
    "Secret": "admin_settings_provider_opt_secret_label",
    "SBP button": "admin_settings_provider_opt_sbp_button_label",
    "SBP method ID": "admin_settings_provider_opt_sbp_method_id_label",
    "Crypto button": "admin_settings_provider_opt_crypto_button_label",
    "Crypto method ID": "admin_settings_provider_opt_crypto_method_id_label",
    "Supported currencies": "admin_settings_provider_opt_supported_currencies_label",
    "Return URL": "admin_settings_provider_opt_return_url_label",
    "Failed URL": "admin_settings_provider_opt_failed_url_label",
    "MID": "admin_settings_provider_opt_mid_label",
    "Token": "admin_settings_provider_opt_token_label",
    "Payment link lifetime (minutes)": (
        "admin_settings_provider_opt_payment_link_lifetime_minutes_label"
    ),
    "Verify webhook signature": "admin_settings_provider_opt_verify_webhook_signature_label",
    "API token": "admin_settings_provider_opt_api_token_label",
    "Terminal ID": "admin_settings_provider_opt_terminal_id_label",
    "Terminal public ID": "admin_settings_provider_opt_terminal_public_id_label",
    "Webhook public key": "admin_settings_provider_opt_webhook_public_key_label",
    "Crypto terminal enabled": "admin_settings_provider_opt_crypto_terminal_enabled_label",
    "Crypto API token": "admin_settings_provider_opt_crypto_api_token_label",
    "Crypto terminal ID": "admin_settings_provider_opt_crypto_terminal_id_label",
    "Crypto terminal public ID": "admin_settings_provider_opt_crypto_terminal_public_id_label",
    "Crypto return URL": "admin_settings_provider_opt_crypto_return_url_label",
    "Crypto failed URL": "admin_settings_provider_opt_crypto_failed_url_label",
    "Crypto link lifetime (minutes)": (
        "admin_settings_provider_opt_crypto_link_lifetime_minutes_label"
    ),
    "Crypto supported currencies": "admin_settings_provider_opt_crypto_supported_currencies_label",
    "Crypto webhook public key": "admin_settings_provider_opt_crypto_webhook_public_key_label",
    "Shop ID": "admin_settings_provider_opt_shop_id_label",
    "Secret key": "admin_settings_provider_opt_secret_key_label",
    "VAT code": "admin_settings_provider_opt_vat_code_label",
    "Network": "admin_settings_provider_opt_network_label",
    "Currency type": "admin_settings_provider_opt_currency_type_label",
    "Asset": "admin_settings_provider_opt_asset_label",
    "Payment API key": "admin_settings_provider_opt_payment_api_key_label",
    "Invoice currency": "admin_settings_provider_opt_invoice_currency_label",
    "Target crypto": "admin_settings_provider_opt_target_crypto_label",
    "Blockchain network": "admin_settings_provider_opt_blockchain_network_label",
    "Success URL": "admin_settings_provider_opt_success_url_label",
    "Invoice lifetime (seconds)": "admin_settings_provider_opt_invoice_lifetime_seconds_label",
    "Widget URL": "admin_settings_provider_opt_widget_url_label",
    "Fallback invoice currency": "admin_settings_provider_opt_fallback_invoice_currency_label",
    "Supported tariff currencies": "admin_settings_provider_opt_supported_tariff_currencies_label",
    "Accepted crypto tickers": "admin_settings_provider_opt_accepted_crypto_tickers_label",
    "Invoice type": "admin_settings_provider_opt_invoice_type_label",
    "Request recvWindow (ms)": "admin_settings_provider_opt_request_recvwindow_ms_label",
    "User pays service fee": "admin_settings_provider_opt_user_pays_service_fee_label",
    "User pays network fee": "admin_settings_provider_opt_user_pays_network_fee_label",
    "Exchange rate URL": "admin_settings_provider_opt_exchange_rate_url_label",
    "Exchange rate cache (seconds)": (
        "admin_settings_provider_opt_exchange_rate_cache_seconds_label"
    ),
    "Minimum payment amount": "admin_settings_provider_opt_minimum_payment_amount_label",
    "Minimum payment currency": "admin_settings_provider_opt_minimum_payment_currency_label",
    "Exact webhook URL": "admin_settings_provider_opt_exact_webhook_url_label",
    "Webhook secret": "admin_settings_provider_opt_webhook_secret_label",
    "Payment services filter": "admin_settings_provider_opt_payment_services_filter_label",
    "Signature token": "admin_settings_provider_opt_signature_token_label",
    "Fail URL": "admin_settings_provider_opt_fail_url_label",
    "Bill lifetime (seconds)": "admin_settings_provider_opt_bill_lifetime_seconds_label",
    "Payer pays commission": "admin_settings_provider_opt_payer_pays_commission_label",
    "Preselected payment method": "admin_settings_provider_opt_preselected_payment_method_label",
    "Payment page locale": "admin_settings_provider_opt_payment_page_locale_label",
    "Payment form title": "admin_settings_provider_opt_payment_form_title_label",
    "Public ID": "admin_settings_provider_opt_public_id_label",
    "API secret": "admin_settings_provider_opt_api_secret_label",
    "Recurring payments": "admin_settings_provider_opt_recurring_payments_label",
    "Checkout URL": "admin_settings_provider_opt_checkout_url_label",
    "Gateway URL": "admin_settings_provider_opt_gateway_url_label",
    "Decline URL": "admin_settings_provider_opt_decline_url_label",
    "Payment page language": "admin_settings_provider_opt_payment_page_language_label",
    "Test mode": "admin_settings_provider_opt_test_mode_label",
    "Recurring enabled": "admin_settings_provider_opt_recurring_enabled_label",
    "Verify webhook auth": "admin_settings_provider_opt_verify_webhook_auth_label",
    "Trusted webhook IPs": "admin_settings_provider_opt_trusted_webhook_ips_label",
    "Cancel URL": "admin_settings_provider_opt_cancel_url_label",
    "Payment method types": "admin_settings_provider_opt_payment_method_types_label",
    "Webhook tolerance seconds": "admin_settings_provider_opt_webhook_tolerance_seconds_label",
    "WebApp button text (RU)": "admin_settings_provider_opt_webapp_button_text_ru_label",
    "WebApp button text (EN)": "admin_settings_provider_opt_webapp_button_text_en_label",
    "WebApp button icon": "admin_settings_provider_opt_webapp_button_icon_label",
    "Telegram button text (RU)": "admin_settings_provider_opt_telegram_button_text_ru_label",
    "Telegram button text (EN)": "admin_settings_provider_opt_telegram_button_text_en_label",
    "Telegram button emoji": "admin_settings_provider_opt_telegram_button_emoji_label",
}

_PROVIDER_OPTION_DESCRIPTION_KEYS: dict[str, str] = {
    "Custom Russian text shown in the Web App payment method button.": (
        "admin_settings_provider_opt_webapp_button_text_ru_description"
    ),
    "Custom English text shown in the Web App payment method button.": (
        "admin_settings_provider_opt_webapp_button_text_en_description"
    ),
    "Lucide icon name rendered inside the Web App payment method button.": (
        "admin_settings_provider_opt_webapp_button_icon_description"
    ),
    "Custom Russian text shown in Telegram bot payment buttons.": (
        "admin_settings_provider_opt_telegram_button_text_ru_description"
    ),
    "Custom English text shown in Telegram bot payment buttons.": (
        "admin_settings_provider_opt_telegram_button_text_en_description"
    ),
    "Emoji prepended to the Telegram bot payment button when customized.": (
        "admin_settings_provider_opt_telegram_button_emoji_description"
    ),
    "See https://merchant.freekassa.net/settings/currencies": (
        "admin_settings_provider_opt_payment_method_id_description"
    ),
    "Public IP address reported to FreeKassa.": (
        "admin_settings_provider_opt_server_ip_description"
    ),
    "Comma-separated IP addresses accepted for FreeKassa webhooks.": (
        "admin_settings_provider_opt_trusted_ips_description"
    ),
    "Comma-separated IP addresses accepted for Wata webhooks.": (
        "admin_settings_provider_opt_trusted_ips_description"
    ),
    "Comma-separated IP addresses accepted for Heleket webhooks.": (
        "admin_settings_provider_opt_trusted_ips_description"
    ),
    "Optional comma-separated IP addresses accepted for PayKilla webhooks.": (
        "admin_settings_provider_opt_trusted_ips_description"
    ),
    "Optional comma-separated IP addresses accepted for CloudPayments webhooks.": (
        "admin_settings_provider_opt_trusted_ips_description"
    ),
    "Optional comma-separated allowlist of webhook source IPs.": (
        "admin_settings_provider_opt_trusted_webhook_ips_description"
    ),
    "Optional internal terminal identifier from the Wata merchant account.": (
        "admin_settings_provider_opt_terminal_id_description"
    ),
    "Optional. Used to validate that Wata webhooks belong to this terminal.": (
        "admin_settings_provider_opt_terminal_public_id_description"
    ),
    "Optional internal crypto terminal identifier from the Wata merchant account.": (
        "admin_settings_provider_opt_crypto_terminal_id_description"
    ),
    "Optional. Used to validate that Wata webhooks belong to the crypto terminal.": (
        "admin_settings_provider_opt_crypto_terminal_public_id_description"
    ),
    "Optional. If empty, the backend fetches it from Wata.": (
        "admin_settings_provider_opt_webhook_public_key_description"
    ),
    "1..6 depending on the tax system": ("admin_settings_provider_opt_vat_code_description"),
    "fiat or crypto.": "admin_settings_provider_opt_currency_type_description",
    "Fiat or crypto code (RUB, USD, USDT).": (
        "admin_settings_provider_opt_invoice_currency_description"
    ),
    "Optional target cryptocurrency for conversion.": (
        "admin_settings_provider_opt_target_crypto_description"
    ),
    "Optional blockchain network code (tron, bsc, eth).": (
        "admin_settings_provider_opt_blockchain_network_description"
    ),
    "PayKilla public HMAC key with INVOICE permission.": (
        "admin_settings_provider_opt_api_key_description"
    ),
    "Validity window for signed PayKilla API requests.": (
        "admin_settings_provider_opt_request_recvwindow_ms_description"
    ),
    "Comma-separated LAVA pay services to show on the payment page (e.g. card,sbp). "
    "Empty shows everything enabled for the shop.": (
        "admin_settings_provider_opt_payment_services_filter_description"
    ),
    "Bearer token from the Pally API integrations page.": (
        "admin_settings_provider_opt_api_token_description"
    ),
    "Token used to verify postback MD5 signatures. Leave empty to use API token.": (
        "admin_settings_provider_opt_signature_token_description"
    ),
    "Optional Pally bill lifetime in seconds.": (
        "admin_settings_provider_opt_bill_lifetime_seconds_description"
    ),
    "Sends payer_pays_commission=1 when enabled.": (
        "admin_settings_provider_opt_payer_pays_commission_description"
    ),
    "Optionally lock the hosted payment form to bank card or SBP.": (
        "admin_settings_provider_opt_preselected_payment_method_description"
    ),
    "Optional payment form locale. Empty follows the user's language where possible.": (
        "admin_settings_provider_opt_payment_page_locale_description"
    ),
    "Optional link name displayed on the Pally payment form.": (
        "admin_settings_provider_opt_payment_form_title_description"
    ),
    "Public ID from the CloudPayments dashboard (HTTP Basic auth username).": (
        "admin_settings_provider_opt_public_id_description"
    ),
    "API Secret from the CloudPayments dashboard. Used as the HTTP Basic auth password "
    "and to verify notification HMAC signatures.": (
        "admin_settings_provider_opt_api_secret_description"
    ),
    "Base URL of the Overpay checkout (payment token) API.": (
        "admin_settings_provider_opt_checkout_url_description"
    ),
    "Base URL of the Overpay gateway API used for saved-token auto-renew charges.": (
        "admin_settings_provider_opt_gateway_url_description"
    ),
    "Optional payment form language code (e.g. ru, en). Empty follows the user's "
    "language where possible.": ("admin_settings_provider_opt_payment_page_language_description"),
    "Sends test transactions to the Overpay sandbox.": (
        "admin_settings_provider_opt_test_mode_description"
    ),
    "Requests a saved card token on checkout and charges it for subscription auto-renew.": (
        "admin_settings_provider_opt_recurring_enabled_description"
    ),
    "Require incoming webhooks to carry the Shop ID / Secret Key HTTP Basic auth.": (
        "admin_settings_provider_opt_verify_webhook_auth_description"
    ),
    "Comma-separated Checkout payment method types. Default: card.": (
        "admin_settings_provider_opt_payment_method_types_description"
    ),
    "Allowed clock skew for Stripe webhook signatures.": (
        "admin_settings_provider_opt_webhook_tolerance_seconds_description"
    ),
}


def _provider_field_i18n_keys(field: SettingField) -> tuple[str, str | None]:
    """Resolve (label_key, description_key) for a provider-owned manifest field.

    Explicit keys on the field win. Otherwise only allowlisted option text
    shares keys across providers; all one-off provider details stay per-field.
    """
    if field.i18n_label_key:
        label_key = field.i18n_label_key
    else:
        label_key = _PROVIDER_OPTION_LABEL_KEYS.get(
            field.label,
            f"admin_settings_field_{field.key.lower()}_label",
        )

    if not field.description:
        description_key = None
    elif field.i18n_description_key:
        description_key = field.i18n_description_key
    else:
        description_key = _PROVIDER_OPTION_DESCRIPTION_KEYS.get(
            field.description,
            f"admin_settings_field_{field.key.lower()}_description",
        )
    return label_key, description_key


def manifest_payload() -> list[dict]:
    """Serialize the manifest for the admin UI.

    For provider presentation fields we resolve the SPEC-declared default
    (e.g. the button text the bot would use if the admin leaves the override
    blank) and expose it as ``default``; ``placeholder`` falls back to the
    same value so existing UIs that only read ``placeholder`` also show the
    hint inside the empty input.
    """
    from bot.payment_providers import (
        find_manifest_owner,
        manifest_field_default,
        provider_admin_metadata,
        provider_admin_only_pairs,
    )

    sections_order = {
        "general": 1,
        "appearance": 2,
        "remnawave": 3,
        "pricing": 11,
        "payments": 4,
        "trial": 5,
        "referral": 6,
        "notifications": 7,
        "email": 8,
        "support": 8,
        "backups": 9,
        "devices": 10,
        "subscription_guides": 10,
        "system": 12,
        "migrations": 13,
    }
    exclusive_map = {
        key: opposite
        for public_key, admin_key in provider_admin_only_pairs()
        for key, opposite in ((public_key, admin_key), (admin_key, public_key))
    }
    items: list[dict] = []
    for field in aggregated_manifest():
        auto_label_i18n_key = f"admin_settings_field_{field.key.lower()}_label"
        auto_description_i18n_key: str | None = (
            f"admin_settings_field_{field.key.lower()}_description"
        )
        auto_subsection_i18n_key = (
            f"admin_settings_subsection_{_i18n_slug(field.subsection)}"
            if field.subsection
            else None
        )

        default_value: str | None = None
        webhook_metadata: dict | None = None
        owner = find_manifest_owner(field.key)
        if owner is not None:
            spec, manifest_field = owner
            default_value = manifest_field_default(spec, manifest_field)
            webhook_metadata = provider_admin_metadata(spec)
            # Provider option labels/descriptions reuse only allowlisted shared keys.
            auto_label_i18n_key, provider_description_key = _provider_field_i18n_keys(field)
            auto_description_i18n_key = provider_description_key

        placeholder = field.placeholder
        if not placeholder and default_value:
            placeholder = default_value

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
            "i18n_subsection_key": field.i18n_subsection_key or auto_subsection_i18n_key,
            "i18n_placeholder_key": (
                f"admin_settings_field_{field.key.lower()}_placeholder" if placeholder else None
            ),
            "placeholder": placeholder,
            "optional": field.optional,
            "secret": field.secret,
        }
        if field.min is not None:
            item["min"] = field.min
        if field.max is not None:
            item["max"] = field.max
        if field.key in exclusive_map:
            item["mutually_exclusive_key"] = exclusive_map[field.key]
        if default_value is not None:
            item["default"] = default_value
        if webhook_metadata:
            item.update(webhook_metadata)
        if field.webhook_path:
            item["webhook_path"] = field.webhook_path
            item["webhook_requires_base_url"] = field.webhook_requires_base_url
            if field.webhook_provider_id:
                item["provider_id"] = field.webhook_provider_id
            if field.webhook_hint_i18n_key:
                item["webhook_hint_i18n_key"] = field.webhook_hint_i18n_key
            if field.webhook_hint:
                item["webhook_hint"] = field.webhook_hint
        if field.choices:
            item["choices"] = [
                {
                    "value": v,
                    "label": lbl,
                    "i18n_label_key": (
                        f"admin_settings_field_{field.key.lower()}_choice_{_i18n_slug(str(v))}"
                    ),
                }
                for v, lbl in field.choices
            ]
        items.append(item)
    return items
