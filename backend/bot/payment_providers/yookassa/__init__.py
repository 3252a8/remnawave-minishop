import logging

from bot.infra import events
from db.dal import payment_dal, user_billing_dal, user_dal

from ..base import (
    PaymentProviderSpec,
    ProviderManifestField,
    ServiceFactoryContext,
    WebAppPaymentContext,
)
from .callbacks import (
    _initiate_yk_payment,
    _yookassa_available_to_callback_user,
    pay_yk_callback_handler,
    pay_yk_new_card_handler,
    pay_yk_saved_list_handler,
    pay_yk_use_saved_handler,
)
from .config import YooKassaConfig, YooKassaPresentation
from .payment_methods import (
    payment_method_bind,
    payment_method_delete,
    payment_method_delete_confirm,
    payment_method_history,
    payment_method_view,
    payment_methods_list,
    payment_methods_manage,
)
from .payments import create_webapp_payment, reuse_webapp_payment
from .router import router
from .service import YooKassaService
from .shared import (
    _format_saved_payment_method_title,
    _format_value,
    _metadata_iso,
    _parse_offer_payload,
    _parse_saved_list_payload,
)
from .success import (
    DEFERRED_EVENTS_KEY,
    DEFERRED_SUCCESS_MESSAGE_KEY,
    HWID_DEVICE_SALE_BASES,
    YOOKASSA_EVENT_PAYMENT_CANCELED,
    YOOKASSA_EVENT_PAYMENT_SUCCEEDED,
    YOOKASSA_EVENT_PAYMENT_WAITING_FOR_CAPTURE,
    YOOKASSA_WEBHOOK_ALLOWED_IPS,
    _is_hwid_device_sale_base,
    _metadata_datetime,
    _metadata_float,
    _metadata_int,
    _metadata_value_present,
    _resolve_yookassa_activation_amounts,
    emit_yookassa_success_events,
    payment_processing_lock,
    process_cancelled_payment,
    process_successful_payment,
)
from .webhook import yookassa_webhook_route

logger = logging.getLogger(__name__)


def create_service(ctx: ServiceFactoryContext) -> YooKassaService:
    bundle = ctx.config_for("yookassa_service")
    config = (
        bundle.config if bundle and isinstance(bundle.config, YooKassaConfig) else YooKassaConfig()
    )
    return YooKassaService(
        shop_id=config.SHOP_ID,
        secret_key=config.SECRET_KEY,
        configured_return_url=config.RETURN_URL,
        bot_username_for_default_return=ctx.bot_username_for_default_return,
        settings_obj=ctx.settings,
        config=config,
        subscription_service=ctx.subscription_service,
    )


_PRESENTATION_MANIFEST = tuple(
    ProviderManifestField(
        key=key,
        type=type_,
        label=label,
        description=description,
        placeholder=placeholder,
        subsection="YooKassa",
        target="presentation",
        attr=attr,
    )
    for key, type_, label, description, placeholder, attr in (
        (
            "PAYMENT_YOOKASSA_WEBAPP_LABEL_RU",
            "string",
            "WebApp button text (RU)",
            "Custom Russian text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_RU",
        ),
        (
            "PAYMENT_YOOKASSA_WEBAPP_LABEL_EN",
            "string",
            "WebApp button text (EN)",
            "Custom English text shown in the Web App payment method button.",
            "",
            "WEBAPP_LABEL_EN",
        ),
        (
            "PAYMENT_YOOKASSA_WEBAPP_ICON",
            "icon",
            "WebApp button icon",
            "Lucide icon name rendered inside the Web App payment method button.",
            "CreditCard",
            "WEBAPP_ICON",
        ),
        (
            "PAYMENT_YOOKASSA_TELEGRAM_LABEL_RU",
            "string",
            "Telegram button text (RU)",
            "Custom Russian text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_RU",
        ),
        (
            "PAYMENT_YOOKASSA_TELEGRAM_LABEL_EN",
            "string",
            "Telegram button text (EN)",
            "Custom English text shown in Telegram bot payment buttons.",
            "",
            "TELEGRAM_LABEL_EN",
        ),
        (
            "PAYMENT_YOOKASSA_TELEGRAM_EMOJI",
            "string",
            "Telegram button emoji",
            "Emoji prepended to the Telegram bot payment button when customized.",
            "💳",
            "TELEGRAM_EMOJI",
        ),
    )
)

_CONFIG_MANIFEST = (
    ProviderManifestField(
        "YOOKASSA_ENABLED", "bool", "Включена", subsection="YooKassa", attr="ENABLED"
    ),
    ProviderManifestField(
        "YOOKASSA_SHOP_ID", "string", "Shop ID", subsection="YooKassa", attr="SHOP_ID"
    ),
    ProviderManifestField(
        "YOOKASSA_SECRET_KEY",
        "string",
        "Secret key",
        subsection="YooKassa",
        secret=True,
        attr="SECRET_KEY",
    ),
    ProviderManifestField(
        "YOOKASSA_RETURN_URL", "url", "Return URL", subsection="YooKassa", attr="RETURN_URL"
    ),
    ProviderManifestField(
        "YOOKASSA_DEFAULT_RECEIPT_EMAIL",
        "string",
        "Email для чека по умолчанию",
        subsection="YooKassa",
        attr="DEFAULT_RECEIPT_EMAIL",
    ),
    ProviderManifestField(
        "YOOKASSA_VAT_CODE",
        "int",
        "VAT code",
        description="1..6 в зависимости от системы налогообложения",
        subsection="YooKassa",
        min=1,
        max=6,
        attr="VAT_CODE",
    ),
    ProviderManifestField(
        "YOOKASSA_AUTOPAYMENTS_ENABLED",
        "bool",
        "Автоплатежи (recurring)",
        subsection="YooKassa",
        attr="AUTOPAYMENTS_ENABLED",
    ),
    ProviderManifestField(
        "YOOKASSA_AUTOPAYMENTS_REQUIRE_CARD_BINDING",
        "bool",
        "Принудительная привязка карты",
        subsection="YooKassa",
        attr="AUTOPAYMENTS_REQUIRE_CARD_BINDING",
    ),
)


SPEC = PaymentProviderSpec(
    id="yookassa",
    provider_key="yookassa",
    label="YooKassa",
    webapp_label="ЮKassa",
    webapp_labels={"ru": "ЮKassa", "en": "YooKassa"},
    webapp_icon="CreditCard",
    telegram_labels={"ru": "ЮKassa", "en": "YooKassa"},
    telegram_emoji="💳",
    pending_status="pending_yookassa",
    enabled=lambda config: bool(getattr(config, "ENABLED", False)),
    service_key="yookassa_service",
    callback_prefix="pay_yk",
    router=router,
    create_service=create_service,
    webhook_path=lambda source: "/webhook/yookassa",
    webhook_route=yookassa_webhook_route,
    webhook_requires_base_url=True,
    create_webapp_payment=create_webapp_payment,
    reuse_webapp_payment=reuse_webapp_payment,
    config_class=YooKassaConfig,
    presentation_class=YooKassaPresentation,
    manifest_fields=_CONFIG_MANIFEST + _PRESENTATION_MANIFEST,
    supports_recurring=True,
    supported_currencies=("RUB",),
    currency_support_note=(
        "YooKassa public payment API examples and limits are RUB-based; "
        "treat non-RUB as unsupported unless your YooKassa contract confirms otherwise."
    ),
    currency_support_url="https://yookassa.ru/developers/payment-acceptance/integration-scenarios/smart-payment",
)

__all__ = [
    "DEFERRED_EVENTS_KEY",
    "DEFERRED_SUCCESS_MESSAGE_KEY",
    "HWID_DEVICE_SALE_BASES",
    "SPEC",
    "YOOKASSA_EVENT_PAYMENT_CANCELED",
    "YOOKASSA_EVENT_PAYMENT_SUCCEEDED",
    "YOOKASSA_EVENT_PAYMENT_WAITING_FOR_CAPTURE",
    "YOOKASSA_WEBHOOK_ALLOWED_IPS",
    "WebAppPaymentContext",
    "YooKassaConfig",
    "YooKassaPresentation",
    "YooKassaService",
    "_format_saved_payment_method_title",
    "_format_value",
    "_initiate_yk_payment",
    "_is_hwid_device_sale_base",
    "_metadata_datetime",
    "_metadata_float",
    "_metadata_int",
    "_metadata_iso",
    "_metadata_value_present",
    "_parse_offer_payload",
    "_parse_saved_list_payload",
    "_resolve_yookassa_activation_amounts",
    "_yookassa_available_to_callback_user",
    "create_service",
    "create_webapp_payment",
    "emit_yookassa_success_events",
    "events",
    "logger",
    "pay_yk_callback_handler",
    "pay_yk_new_card_handler",
    "pay_yk_saved_list_handler",
    "pay_yk_use_saved_handler",
    "payment_dal",
    "payment_method_bind",
    "payment_method_delete",
    "payment_method_delete_confirm",
    "payment_method_history",
    "payment_method_view",
    "payment_methods_list",
    "payment_methods_manage",
    "payment_processing_lock",
    "process_cancelled_payment",
    "process_successful_payment",
    "reuse_webapp_payment",
    "router",
    "user_billing_dal",
    "user_dal",
    "yookassa_webhook_route",
]
