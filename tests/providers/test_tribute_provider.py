from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, TypedDict, cast
from unittest.mock import AsyncMock

import pytest
from aiohttp import web

from bot.app.web.webapp import billing_payments
from bot.payment_providers.base import ProviderWebhookPayload, WebAppPaymentContext
from bot.payment_providers.shared import build_entitlement_context_snapshot
from bot.payment_providers.tribute import service as tribute_service
from bot.payment_providers.tribute.models import (
    TributeSubscriptionPayload,
    TributeWebhookEnvelope,
)
from bot.payment_providers.tribute.service import (
    TRIBUTE_SERVICE_KEY,
    TributeConfig,
    TributePlanBinding,
    TributeService,
)
from bot.payment_providers.tribute.shop import (
    TributeShopOrderResponse,
    TributeShopTransactionsResponse,
    tribute_shop_major_to_minor,
)
from bot.services.subscription_service_impl.tariff_change_quote import (
    build_tariff_change_quote_snapshot,
)
from config.tariffs_config import TributeProductConfig, TributeTariffConfig

API_KEY = "tribute-api-key"
SHOP_ID = 731
CREATED_AT = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)
EXPIRES_AT = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
SHOP_ORDER_UUID = "550e8400-e29b-41d4-a716-446655440000"
SHOP_PAYMENT_TOKEN = "660e8400-e29b-41d4-a716-446655440001"


class _ShopPaymentOptions(TypedDict, total=False):
    payment_id: int
    status: str
    amount: float
    currency: str
    sale_mode: str
    tariff_key: str | None
    months: int
    purchased_gb: float | None
    purchased_hwid_devices: int | None
    provider_payment_id: str
    checkout_base_amount: float | None
    tariff_change_quote_snapshot: str | None
    entitlement_context_snapshot: str | None


class _ShopPayloadOptions(TypedDict, total=False):
    amount: int
    currency: str
    period: str
    is_recurrent: bool
    status: str
    order_uuid: str
    first_period_amount: int | None


class _FakeSession:
    def __init__(self) -> None:
        self.commit = AsyncMock()
        self.flush = AsyncMock()
        self.rollback = AsyncMock()

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class _TariffsConfig:
    def __init__(self, tariffs: list[SimpleNamespace]) -> None:
        self.tariffs = tariffs

    def require(self, key: str) -> SimpleNamespace:
        tariff = next(
            (candidate for candidate in self.tariffs if candidate.key == key),
            None,
        )
        if tariff is None:
            raise KeyError(key)
        return tariff

    require_configured = require

    def tribute_product_target(
        self,
        product_id: int,
    ) -> tuple[SimpleNamespace, str, float] | None:
        for tariff in self.tariffs:
            tribute = getattr(tariff, "tribute", None)
            if tribute is None:
                continue
            for kind, products in (
                ("traffic", getattr(tribute, "traffic_products", {})),
                (
                    "premium_traffic",
                    getattr(tribute, "premium_traffic_products", {}),
                ),
            ):
                for units, product in products.items():
                    if int(product.product_id) == int(product_id):
                        return tariff, kind, float(units)
        return None


class _FakeRequest:
    def __init__(self, body: bytes, signature: str = "") -> None:
        self._body = body
        self.read_mock: AsyncMock | None = None
        self.headers = {"trbt-signature": signature} if signature else {}
        self.content_length: int | None = len(body)
        self.app: dict[str, object] = {}

    async def read(self) -> bytes:
        if self.read_mock is not None:
            return cast(bytes, await self.read_mock())
        return self._body


def _hmac_hex(body: bytes, key: str = API_KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _tariff(
    *,
    key: str = "pro",
    billing_model: str = "period",
    subscription_id: int | None = 101,
    link: str | None = "https://t.me/tribute/app?startapp=subscription",
    period_ids: dict[str, int] | None = None,
    period_links: dict[str, str] | None = None,
    period_subscription_ids: dict[str, int] | None = None,
    traffic_products: dict[str, SimpleNamespace] | None = None,
    premium_traffic_products: dict[str, SimpleNamespace] | None = None,
) -> SimpleNamespace:
    """A tariff whose ``tribute`` block is the real model, not a stand-in.

    Period-to-subscription resolution lives in TributeTariffConfig, so the
    checkout and webhook bindings must be exercised against it.
    """

    return SimpleNamespace(
        key=key,
        billing_model=billing_model,
        tribute=TributeTariffConfig(
            link=link,
            subscription_id=subscription_id,
            period_ids=period_ids or {"1": 201, "3": 203},
            period_links=period_links or {},
            period_subscription_ids=period_subscription_ids or {},
            traffic_products={
                units: TributeProductConfig(product_id=item.product_id, link=item.link)
                for units, item in (traffic_products or {}).items()
            },
            premium_traffic_products={
                units: TributeProductConfig(product_id=item.product_id, link=item.link)
                for units, item in (premium_traffic_products or {}).items()
            },
        ),
    )


def _settings(*tariffs: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(tariffs_config=_TariffsConfig(list(tariffs or (_tariff(),))))


def _digital_settings() -> SimpleNamespace:
    product = lambda product_id, link: SimpleNamespace(product_id=product_id, link=link)
    return _settings(
        _tariff(
            key="traffic",
            billing_model="traffic",
            traffic_products={
                "50": product(501, "https://t.me/tribute/app?startapp=p501"),
            },
        ),
        _tariff(
            key="pro",
            traffic_products={
                "10": product(502, "https://web.tribute.tg/p/502"),
            },
            premium_traffic_products={
                "5": product(503, "https://t.me/tribute/app?startapp=p503"),
            },
        ),
    )


def _service(
    *,
    settings: SimpleNamespace | None = None,
    config: TributeConfig | None = None,
    session: _FakeSession | None = None,
) -> TributeService:
    service = object.__new__(TributeService)
    service.bot = SimpleNamespace()
    service.settings = settings or _settings()
    service.config = config or TributeConfig(
        ENABLED=True,
        API_KEY=API_KEY,
        SHOP_ID=SHOP_ID,
    )
    service.i18n = SimpleNamespace()
    service.subscription_service = SimpleNamespace()
    service.referral_service = SimpleNamespace()
    service.async_session_factory = lambda: session or _FakeSession()
    return service


def _payload(
    *,
    subscription_id: int = 101,
    period_id: int = 201,
    price: int = 1234,
    amount: int = 987,
    subscription_type: str = "regular",
    expires_at: datetime = EXPIRES_AT,
    telegram_user_id: int = 42,
) -> TributeSubscriptionPayload:
    return TributeSubscriptionPayload.model_validate(
        {
            "subscription_name": "Pro access",
            "subscription_id": subscription_id,
            "period_id": period_id,
            "period": "monthly",
            "price": price,
            "amount": amount,
            "currency": "rub",
            "user_id": 1,
            "trb_user_id": "tribute-user-42",
            "telegram_user_id": telegram_user_id,
            "telegram_username": "subscriber",
            "channel_id": -100123,
            "channel_name": "Creator",
            "expires_at": expires_at,
            "type": subscription_type,
        }
    )


def _digital_product_payload(
    *,
    product_id: int = 501,
    purchase_id: int = 7001,
    transaction_id: int = 9001,
    amount: int = 14900,
    currency: str = "rub",
    telegram_user_id: int | None = 42,
    trb_user_id: str | None = "T-42",
    purchase_created_at: datetime = CREATED_AT,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "product_id": product_id,
        "product_name": "Traffic package",
        "amount": amount,
        "currency": currency,
        "purchase_id": purchase_id,
        "transaction_id": transaction_id,
        "purchase_created_at": purchase_created_at.isoformat(),
    }
    if telegram_user_id is not None:
        payload["telegram_user_id"] = telegram_user_id
    if trb_user_id is not None:
        payload["trb_user_id"] = trb_user_id
    return payload


def _digital_refund_payload(
    *,
    product_id: int = 501,
    purchase_id: int = 7001,
    transaction_id: int = 9001,
    amount: int = 14900,
    currency: str = "rub",
    telegram_user_id: int | None = 42,
    trb_user_id: str | None = "T-42",
    refunded_at: datetime = EXPIRES_AT,
) -> dict[str, object]:
    payload = _digital_product_payload(
        product_id=product_id,
        purchase_id=purchase_id,
        transaction_id=transaction_id,
        amount=amount,
        currency=currency,
        telegram_user_id=telegram_user_id,
        trb_user_id=trb_user_id,
    )
    payload.pop("purchase_created_at")
    payload["refund_reason"] = "customer_request"
    payload["refunded_at"] = refunded_at.isoformat()
    return payload


def _shop_payload(
    *,
    amount: int = 14900,
    currency: str = "rub",
    period: str = "onetime",
    is_recurrent: bool = False,
    status: str = "paid",
    order_uuid: str = SHOP_ORDER_UUID,
    first_period_amount: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "uuid": order_uuid,
        "shopId": SHOP_ID,
        "amount": amount,
        "currency": currency,
        "fee": 1200,
        "status": status,
        "isRecurrent": is_recurrent,
        "period": period,
        "paymentToken": SHOP_PAYMENT_TOKEN,
        "cardLast4": "4242",
        "cardBrand": "VISA",
    }
    if first_period_amount is not None:
        payload["firstPeriodAmount"] = first_period_amount
    return payload


def _shop_charge_payload(
    *,
    amount: int = 9900,
    currency: str = "rub",
    period: str = "monthly",
    order_uuid: str = SHOP_ORDER_UUID,
    first_period_amount: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "uuid": order_uuid,
        "shopId": SHOP_ID,
        "amount": amount,
        "currency": currency,
        "period": period,
    }
    if first_period_amount is not None:
        payload["firstPeriodAmount"] = first_period_amount
    return payload


def _shop_refund_payload(
    *,
    amount: int = 14900,
    currency: str = "rub",
    order_uuid: str = SHOP_ORDER_UUID,
    transaction_id: int = 12345,
    status: str = "initiated",
    first_period_amount: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "uuid": order_uuid,
        "shopId": SHOP_ID,
        "transactionId": transaction_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "refundedAt": EXPIRES_AT.isoformat(),
    }
    if first_period_amount is not None:
        payload["firstPeriodAmount"] = first_period_amount
    return payload


def _shop_order_response(
    *,
    amount: int = 14900,
    currency: str = "rub",
    period: str = "onetime",
    status: str = "pending",
    shop_id: int = SHOP_ID,
    first_period_amount: int | None = None,
    payment_url: str | None = "https://tribute.tg/shop/pay/order",
    webapp_payment_url: str = "https://t.me/tribute/app?startapp=shop-order",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "uuid": SHOP_ORDER_UUID,
        "shopId": shop_id,
        "amount": amount,
        "currency": currency,
        "status": status,
        "period": period,
        "paymentUrl": payment_url,
        "webappPaymentUrl": webapp_payment_url,
    }
    if first_period_amount is not None:
        payload["firstPeriodAmount"] = first_period_amount
    return payload


def _verified_event_payload(
    name: str,
    payload: dict[str, object],
    *,
    created_at: datetime = CREATED_AT,
    sent_at: datetime | None = None,
) -> ProviderWebhookPayload:
    body = json.dumps(
        {
            "name": name,
            "created_at": created_at.isoformat(),
            "sent_at": (sent_at or created_at + timedelta(seconds=1)).isoformat(),
            "payload": payload,
        },
        separators=(",", ":"),
    ).encode()
    return ProviderWebhookPayload(raw_body=body)


def _envelope(
    name: str,
    payload: TributeSubscriptionPayload,
    *,
    created_at: datetime = CREATED_AT,
    sent_at: datetime | None = None,
) -> TributeWebhookEnvelope:
    return TributeWebhookEnvelope.model_validate(
        {
            "name": name,
            "created_at": created_at,
            "sent_at": sent_at or created_at + timedelta(seconds=1),
            "payload": payload.model_dump(mode="json"),
        }
    )


def _entitlement(
    *,
    last_event_name: str = "new_subscription",
    last_event_created_at: datetime = CREATED_AT - timedelta(days=1),
    last_event_fingerprint: str = "older-fingerprint",
    status: str = "active",
    active_until: datetime = EXPIRES_AT - timedelta(days=1),
    subscription_type: str = "regular",
) -> SimpleNamespace:
    return SimpleNamespace(
        tribute_subscription_id=101,
        tribute_period_id=201,
        trb_user_id="tribute-user-42",
        telegram_user_id=42,
        user_id=42,
        tariff_key="pro",
        duration_months=1,
        subscription_type=subscription_type,
        status=status,
        active_until=active_until,
        last_event_name=last_event_name,
        last_event_created_at=last_event_created_at,
        last_event_fingerprint=last_event_fingerprint,
    )


def _event(status: str = "processing") -> SimpleNamespace:
    return SimpleNamespace(
        event_id=1,
        status=status,
        status_reason=None,
        payment_id=None,
        processed_at=None,
    )


def _payment(status: str = "pending_tribute") -> SimpleNamespace:
    return SimpleNamespace(
        payment_id=55,
        status=status,
        amount=12.34,
        currency="RUB",
        sale_mode="subscription@pro",
    )


def _digital_payment(
    *,
    status: str = "pending_tribute",
    sale_mode: str = "traffic_package@traffic",
    tariff_key: str = "traffic",
    purchased_gb: float = 50,
    entitlement_context_snapshot: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        payment_id=75,
        user_id=42,
        status=status,
        amount=149.0,
        currency="RUB",
        provider="tribute",
        provider_payment_id="digital_product:7001",
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        subscription_duration_months=int(purchased_gb),
        purchased_gb=purchased_gb,
        purchased_hwid_devices=None,
        entitlement_context_snapshot=entitlement_context_snapshot,
    )


def _shop_payment(
    *,
    payment_id: int = 85,
    status: str = "pending_tribute",
    amount: float = 149.0,
    currency: str = "RUB",
    sale_mode: str = "traffic_package@traffic",
    tariff_key: str | None = "traffic",
    months: int = 50,
    purchased_gb: float | None = 50,
    purchased_hwid_devices: int | None = None,
    provider_payment_id: str = SHOP_ORDER_UUID,
    checkout_base_amount: float | None = None,
    tariff_change_quote_snapshot: str | None = None,
    entitlement_context_snapshot: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        payment_id=payment_id,
        user_id=42,
        status=status,
        amount=amount,
        currency=currency,
        provider="tribute",
        provider_payment_id=provider_payment_id,
        provider_payment_url="https://t.me/tribute/app?startapp=shop-order",
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        subscription_duration_months=months,
        purchased_gb=purchased_gb,
        purchased_hwid_devices=purchased_hwid_devices,
        checkout_base_amount=checkout_base_amount,
        tariff_change_quote_snapshot=tariff_change_quote_snapshot,
        entitlement_context_snapshot=entitlement_context_snapshot,
        is_auto_renew=False,
        renewal_subscription_id=None,
        renewal_cycle_end=None,
    )


def _quoted_tariff_upgrade_payment(
    *,
    source_tariff_key: str = "basic",
    target_tariff_key: str = "pro",
    amount: float = 75.5,
    currency: str = "RUB",
) -> SimpleNamespace:
    return _shop_payment(
        amount=amount,
        currency=currency,
        sale_mode=f"tariff_upgrade@{target_tariff_key}",
        tariff_key=target_tariff_key,
        months=1,
        purchased_gb=None,
        tariff_change_quote_snapshot=build_tariff_change_quote_snapshot(
            source_tariff_key=source_tariff_key,
            target_tariff_key=target_tariff_key,
            required_amount=amount,
            currency=currency,
            convertible_hwid_purchase_ids=[],
        ),
    )


def _active_tariff_subscription(tariff_key: str) -> SimpleNamespace:
    return SimpleNamespace(
        subscription_id=501,
        user_id=42,
        tariff_key=tariff_key,
        provider="yookassa",
        auto_renew_enabled=False,
    )


def _product_purchase(
    *,
    status: str = "processing",
    product_id: int = 501,
    purchase_id: int = 7001,
    transaction_id: int = 9001,
    telegram_user_id: int | None = 42,
    user_id: int | None = 42,
    sale_mode: str | None = "traffic_package@traffic",
    tariff_key: str | None = "traffic",
    units: float | None = 50,
    payment_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        purchase_row_id=1,
        tribute_purchase_id=purchase_id,
        tribute_transaction_id=transaction_id,
        tribute_product_id=product_id,
        trb_user_id="T-42" if telegram_user_id is not None else None,
        telegram_user_id=telegram_user_id,
        user_id=user_id,
        tariff_key=tariff_key,
        sale_mode=sale_mode,
        units=units,
        amount=14900,
        currency="RUB",
        status=status,
        status_reason=None,
        payment_id=payment_id,
        purchase_created_at=CREATED_AT,
        fulfilled_at=None,
        refunded_at=None,
        refund_reason=None,
    )


def _shop_event(
    status: str = "processing",
    *,
    event_name: str = "shop_order",
    payment_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        event_id=2,
        fingerprint="f" * 64,
        event_name=event_name,
        order_uuid=SHOP_ORDER_UUID,
        status=status,
        status_reason=None,
        payment_id=payment_id,
        processed_at=None,
    )


def _response_json(response) -> dict[str, object]:
    return cast(dict[str, object], json.loads(response.body))


def _install_event_mocks(
    monkeypatch,
    service: TributeService,
    *,
    event: SimpleNamespace,
    entitlement: SimpleNamespace | None,
    payment: SimpleNamespace | None = None,
    user: SimpleNamespace | None = None,
) -> SimpleNamespace:
    # Tribute knows a Telegram ID; the webhook resolves it to the local
    # account and works with that identity from then on.
    user = user or SimpleNamespace(user_id=42, telegram_id=42)
    mocks = SimpleNamespace(
        user=AsyncMock(return_value=user),
        user_by_telegram=AsyncMock(return_value=user),
        ensure_event=AsyncMock(return_value=(event, True)),
        get_entitlement=AsyncMock(return_value=entitlement),
        active_shop_order=AsyncMock(return_value=None),
        active_creator_subscription=AsyncMock(return_value=None),
        create_entitlement=AsyncMock(),
        ensure_payment=AsyncMock(return_value=payment or _payment()),
        claim=AsyncMock(return_value=payment or _payment()),
        get_payment=AsyncMock(return_value=payment or _payment("succeeded")),
        finalize=AsyncMock(return_value=SimpleNamespace()),
        enable=AsyncMock(),
        disable=AsyncMock(),
    )

    async def create_entitlement(_session, values):
        return SimpleNamespace(**values)

    mocks.create_entitlement.side_effect = create_entitlement
    monkeypatch.setattr(tribute_service.user_dal, "lock_user_by_id", mocks.user)
    monkeypatch.setattr(
        tribute_service.user_dal,
        "get_user_by_telegram_id",
        mocks.user_by_telegram,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "ensure_webhook_event",
        mocks.ensure_event,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_entitlement_for_update",
        mocks.get_entitlement,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_shop_order_uuid",
        mocks.active_shop_order,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_creator_subscription_id",
        mocks.active_creator_subscription,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "create_entitlement",
        mocks.create_entitlement,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "claim_payment_finalization",
        mocks.claim,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "get_payment_by_db_id",
        mocks.get_payment,
    )
    monkeypatch.setattr(tribute_service, "finalize_successful_payment", mocks.finalize)
    monkeypatch.setattr(service, "_ensure_payment", mocks.ensure_payment)
    monkeypatch.setattr(service, "_enable_local_auto_renew", mocks.enable)
    monkeypatch.setattr(service, "_disable_local_auto_renew", mocks.disable)
    return mocks


def _install_product_mocks(
    monkeypatch,
    service: TributeService,
    *,
    purchase: SimpleNamespace,
    payment: SimpleNamespace | None = None,
    user: SimpleNamespace | None = None,
) -> SimpleNamespace:
    resolved_payment = payment or _digital_payment()
    sale_base = str(purchase.sale_mode or "").split("@", 1)[0]
    active_subscription = (
        None
        if sale_base == "traffic_package"
        else SimpleNamespace(
            subscription_id=91,
            tariff_key=purchase.tariff_key,
        )
    )
    resolved_user = user or SimpleNamespace(user_id=42, telegram_id=42)
    mocks = SimpleNamespace(
        user=AsyncMock(return_value=resolved_user),
        user_by_telegram=AsyncMock(return_value=resolved_user),
        ensure_purchase=AsyncMock(return_value=(purchase, True)),
        get_purchase=AsyncMock(return_value=purchase),
        ensure_payment=AsyncMock(return_value=resolved_payment),
        claim=AsyncMock(return_value=resolved_payment),
        get_payment=AsyncMock(return_value=resolved_payment),
        update_payment_status=AsyncMock(),
        finalize=AsyncMock(return_value=SimpleNamespace()),
        active_subscription=AsyncMock(return_value=active_subscription),
    )
    monkeypatch.setattr(tribute_service.user_dal, "get_user_by_id", mocks.user)
    monkeypatch.setattr(tribute_service.user_dal, "lock_user_by_id", mocks.user)
    monkeypatch.setattr(
        tribute_service.user_dal,
        "get_user_by_telegram_id",
        mocks.user_by_telegram,
    )
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        mocks.active_subscription,
    )
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id_for_update",
        mocks.active_subscription,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "ensure_product_purchase",
        mocks.ensure_purchase,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_product_purchase_for_update",
        mocks.get_purchase,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "ensure_payment_with_provider_id",
        mocks.ensure_payment,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "claim_payment_finalization",
        mocks.claim,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "get_payment_by_db_id",
        mocks.get_payment,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "update_payment_status_by_db_id",
        mocks.update_payment_status,
    )
    monkeypatch.setattr(tribute_service, "finalize_successful_payment", mocks.finalize)
    return mocks


def _install_shop_mocks(
    monkeypatch,
    service: TributeService,
    *,
    payment: SimpleNamespace,
    event: SimpleNamespace | None = None,
    cycle_payment: SimpleNamespace | None = None,
) -> SimpleNamespace:
    resolved_event = event or _shop_event()
    payment_sale_base = str(payment.sale_mode or "").split("@", 1)[0]
    active_subscription = (
        SimpleNamespace(
            subscription_id=501,
            tariff_key=payment.tariff_key,
        )
        if payment_sale_base in {"topup", "premium_topup", "hwid_device", "hwid_devices"}
        else None
    )
    resolved_cycle = cycle_payment or _shop_payment(
        payment_id=86,
        status="pending_tribute",
        amount=payment.amount,
        currency=payment.currency,
        sale_mode=payment.sale_mode,
        tariff_key=payment.tariff_key,
        months=payment.subscription_duration_months,
        purchased_gb=payment.purchased_gb,
        purchased_hwid_devices=payment.purchased_hwid_devices,
        provider_payment_id="shop_charge:" + ("a" * 64),
    )

    def latest_recurring_state(_session: object, _order_uuid: str) -> str | None:
        event_name = str(resolved_event.event_name)
        if event_name in {"shop_order", "shop_order_charge_success"}:
            return "active"
        if event_name == "shop_order_cancelled":
            return "inactive"
        if (
            event_name == "shop_order_charge_failed"
            and resolved_event.status_reason == "charge_retry_3"
        ):
            return "inactive"
        return None

    mocks = SimpleNamespace(
        initial_payment=payment,
        cycle_payment=resolved_cycle,
        ensure_event=AsyncMock(return_value=(resolved_event, True)),
        recurring_state=AsyncMock(side_effect=latest_recurring_state),
        user=AsyncMock(return_value=SimpleNamespace(user_id=payment.user_id)),
        active_shop_order=AsyncMock(return_value=None),
        active_creator_subscription=AsyncMock(return_value=None),
        quarantine_reason=AsyncMock(return_value=None),
        success_tombstone=AsyncMock(return_value=None),
        cancel_order=AsyncMock(return_value=True),
        refund_order=AsyncMock(return_value="initiated"),
        lookup=AsyncMock(return_value=payment),
        ensure_cycle=AsyncMock(return_value=resolved_cycle),
        claim=AsyncMock(return_value=payment),
        get_payment=AsyncMock(return_value=payment),
        update_payment_status=AsyncMock(),
        finalize=AsyncMock(return_value=SimpleNamespace()),
        active_subscription=AsyncMock(return_value=active_subscription),
        set_auto_renew=AsyncMock(),
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "ensure_shop_webhook_event",
        mocks.ensure_event,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_shop_recurring_state",
        mocks.recurring_state,
    )
    monkeypatch.setattr(tribute_service.user_dal, "lock_user_by_id", mocks.user)
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_shop_order_uuid",
        mocks.active_shop_order,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_creator_subscription_id",
        mocks.active_creator_subscription,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_shop_order_quarantine_reason",
        mocks.quarantine_reason,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_shop_success_tombstone_reason",
        mocks.success_tombstone,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "get_payment_by_provider_payment_id",
        mocks.lookup,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "ensure_payment_with_provider_id",
        mocks.ensure_cycle,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "claim_payment_finalization",
        mocks.claim,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "get_payment_by_db_id",
        mocks.get_payment,
    )
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "update_payment_status_by_db_id",
        mocks.update_payment_status,
    )
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        mocks.active_subscription,
    )
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id_for_update",
        mocks.active_subscription,
    )
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "set_auto_renew",
        mocks.set_auto_renew,
    )
    monkeypatch.setattr(service, "_cancel_shop_order", mocks.cancel_order)
    monkeypatch.setattr(
        service,
        "_refund_shop_order_exact_sell",
        mocks.refund_order,
    )
    monkeypatch.setattr(tribute_service, "finalize_successful_payment", mocks.finalize)
    return mocks


def test_signature_is_over_the_exact_raw_body() -> None:
    service = _service()
    compact = b'{"name":"new_subscription","payload":{"price":1234}}'
    spaced = b'{"name": "new_subscription", "payload": {"price": 1234}}'

    assert service.verify_signature(
        ProviderWebhookPayload(raw_body=compact, signature=_hmac_hex(compact))
    )
    assert not service.verify_signature(
        ProviderWebhookPayload(raw_body=spaced, signature=_hmac_hex(compact))
    )


def test_oversized_webhook_body_is_refused_before_it_is_read() -> None:
    """A signature is computed over the whole body, so the body is bounded."""

    service = _service()
    oversized = b"{}" + b" " * tribute_service.TRIBUTE_MAX_WEBHOOK_BYTES
    request = _FakeRequest(oversized, _hmac_hex(oversized))
    request.read_mock = AsyncMock(side_effect=AssertionError("body must not be read"))

    with pytest.raises(web.HTTPRequestEntityTooLarge):
        asyncio.run(service.parse_payload(cast(Any, request)))


def test_oversized_webhook_body_is_refused_when_length_is_not_declared() -> None:
    service = _service()
    oversized = b"{}" + b" " * tribute_service.TRIBUTE_MAX_WEBHOOK_BYTES
    request = _FakeRequest(oversized, _hmac_hex(oversized))
    request.content_length = None

    with pytest.raises(web.HTTPRequestEntityTooLarge):
        asyncio.run(service.parse_payload(cast(Any, request)))


@pytest.mark.parametrize("signature", ["", "abcd", "g" * 64, "00" * 31])
def test_signature_rejects_missing_or_malformed_hex(signature: str) -> None:
    service = _service()

    assert not service.verify_signature(ProviderWebhookPayload(raw_body=b"{}", signature=signature))


@pytest.mark.parametrize("event_name", ["new_donation", "recurrent_donation"])
def test_signed_donation_webhook_is_ignored_without_payment_side_effects(
    monkeypatch,
    event_name: str,
) -> None:
    service = _service()
    process_subscription = AsyncMock()
    process_product = AsyncMock()
    process_refund = AsyncMock()
    process_shop = AsyncMock()
    monkeypatch.setattr(service, "_process_subscription_event", process_subscription)
    monkeypatch.setattr(service, "_process_digital_product_purchase", process_product)
    monkeypatch.setattr(service, "_process_digital_product_refund", process_refund)
    monkeypatch.setattr(service, "_process_shop_event", process_shop)
    body = json.dumps(
        {
            "name": event_name,
            "created_at": CREATED_AT.isoformat(),
            "sent_at": (CREATED_AT + timedelta(seconds=1)).isoformat(),
            "payload": {
                "amount": 14900,
                "currency": "rub",
                "telegram_user_id": 42,
            },
        },
        separators=(",", ":"),
    ).encode()
    request = _FakeRequest(body, _hmac_hex(body))

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 200
    assert _response_json(response) == {"ok": True, "status": "ignored"}
    process_subscription.assert_not_awaited()
    process_product.assert_not_awaited()
    process_refund.assert_not_awaited()
    process_shop.assert_not_awaited()


@pytest.mark.parametrize(
    "event_name",
    ["shop_order_payment_received", "shop_order_prepaid"],
)
def test_shop_intermediate_webhook_waits_for_final_order_before_fulfillment(
    monkeypatch,
    event_name: str,
) -> None:
    service = _service()
    process_subscription = AsyncMock()
    process_product = AsyncMock()
    process_refund = AsyncMock()
    process_shop = AsyncMock()
    monkeypatch.setattr(service, "_process_subscription_event", process_subscription)
    monkeypatch.setattr(service, "_process_digital_product_purchase", process_product)
    monkeypatch.setattr(service, "_process_digital_product_refund", process_refund)
    monkeypatch.setattr(service, "_process_shop_event", process_shop)
    body = json.dumps(
        {
            "name": event_name,
            "created_at": CREATED_AT.isoformat(),
            "sent_at": (CREATED_AT + timedelta(seconds=1)).isoformat(),
            "payload": {
                "uuid": SHOP_ORDER_UUID,
                "shopId": SHOP_ID,
                "amount": 14900,
                "currency": "rub",
            },
        },
        separators=(",", ":"),
    ).encode()
    request = _FakeRequest(body, _hmac_hex(body))

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 200
    assert _response_json(response) == {"ok": True, "status": "ignored"}
    process_subscription.assert_not_awaited()
    process_product.assert_not_awaited()
    process_refund.assert_not_awaited()
    process_shop.assert_not_awaited()


def test_config_fails_closed_without_both_enablement_and_api_key() -> None:
    assert not _service(config=TributeConfig(ENABLED=False, API_KEY=API_KEY)).configured
    assert not _service(config=TributeConfig(ENABLED=True, API_KEY=None)).configured
    assert not _service(config=TributeConfig(ENABLED=True, API_KEY="   ")).configured
    assert _service(config=TributeConfig(ENABLED=True, API_KEY=API_KEY)).configured
    assert _service(
        config=TributeConfig(
            ENABLED=False,
            ADMIN_ONLY_ENABLED=True,
            API_KEY=API_KEY,
        )
    ).configured


def test_shop_flag_without_shop_id_warns_and_keeps_shop_orders_off(caplog) -> None:
    # Refusing to construct turned an incomplete-but-legal env into a boot
    # failure of the whole app, while the runtime already downgrades it to
    # Creator-only selling.
    with caplog.at_level(logging.WARNING, logger="bot.payment_providers.tribute.config"):
        config = TributeConfig(ENABLED=True, API_KEY=API_KEY, SHOP_ENABLED=True)

    assert config.SHOP_ENABLED is True
    assert config.SHOP_ID is None
    assert not _service(config=config).shop_enabled
    assert "TRIBUTE_SHOP_ENABLED is on without TRIBUTE_SHOP_ID" in caplog.text


@pytest.mark.parametrize(
    "shop_id",
    [0, -1, 2**64, True, 1.5, "1.5", "not-an-id"],
)
def test_shop_config_rejects_non_positive_or_non_integer_shop_id(shop_id: object) -> None:
    with pytest.raises(ValueError):
        TributeConfig.model_validate(
            {
                "ENABLED": True,
                "API_KEY": API_KEY,
                "SHOP_ENABLED": True,
                "SHOP_ID": shop_id,
            }
        )


def test_shop_config_accepts_trimmed_positive_shop_id() -> None:
    config = TributeConfig.model_validate(
        {
            "ENABLED": True,
            "API_KEY": API_KEY,
            "SHOP_ENABLED": True,
            "SHOP_ID": f"  {SHOP_ID}  ",
        }
    )

    assert config.SHOP_ID == SHOP_ID


def test_disabled_webhook_returns_503_before_reading_body() -> None:
    service = _service(config=TributeConfig(ENABLED=False, API_KEY=API_KEY))
    request = _FakeRequest(b"{}")
    read = AsyncMock(side_effect=AssertionError("disabled provider must not read body"))
    request.read_mock = read

    response = asyncio.run(service.webhook_route(request))

    assert response.status == 503
    read.assert_not_awaited()


def test_event_fingerprint_ignores_retry_sent_at_but_not_event_time() -> None:
    payload = _payload()
    first = _envelope(
        "new_subscription",
        payload,
        sent_at=CREATED_AT + timedelta(minutes=1),
    )
    retry = _envelope(
        "new_subscription",
        payload,
        sent_at=CREATED_AT + timedelta(hours=8),
    )
    distinct = _envelope(
        "new_subscription",
        payload,
        created_at=CREATED_AT + timedelta(microseconds=1),
    )

    assert tribute_service._event_fingerprint(
        first,
        payload,
    ) == tribute_service._event_fingerprint(retry, payload)
    assert tribute_service._event_fingerprint(
        first,
        payload,
    ) != tribute_service._event_fingerprint(distinct, payload)


def test_checkout_returns_only_the_configured_link_for_the_selected_period(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=None),
    )
    service = _service()
    request = SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service})
    context = WebAppPaymentContext(
        request=request,
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=3,
        price=1.0,
        stars_price=None,
        description="Local price is not authoritative",
        sale_mode="subscription@pro",
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert tribute_service.SPEC.price_managed_externally is False
    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "action": "open_link",
        "payment_url": "https://t.me/tribute/app?startapp=subscription",
        "payment_id": None,
    }


def test_creator_fixed_link_checkout_rejects_local_promo(monkeypatch) -> None:
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=None),
    )
    service = _service()
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=3,
        price=1.0,
        stars_price=None,
        description="Local promo cannot alter a Creator link",
        sale_mode="subscription@pro",
        promo_code_id=7,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response.status == 400
    assert _response_json(response)["error"] == "payment_unavailable"


def test_provider_currency_filter_matches_shop_contract() -> None:
    assert tribute_service.SPEC.is_usable_for_payment_currency(SimpleNamespace(), "RUB")
    assert not tribute_service.SPEC.is_usable_for_payment_currency(SimpleNamespace(), "KZT")


def test_shop_checkout_uses_creator_link_for_unsupported_recurring_period(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=None),
    )
    service = _service(
        settings=_settings(_tariff(period_ids={"2": 202})),
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        ),
    )
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=2,
        price=199.0,
        stars_price=None,
        description="Two-month Creator fallback",
        sale_mode="subscription@pro",
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "action": "open_link",
        "payment_url": "https://t.me/tribute/app?startapp=subscription",
        "payment_id": None,
    }


def test_shop_webapp_allows_first_cycle_promo_for_recurring_checkout(monkeypatch) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock(return_value=None)
    expected_response = object()
    run_payment = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=1,
        price=149.0,
        stars_price=None,
        description="Discounted recurring checkout",
        sale_mode="subscription@pro",
        promo_code_id=7,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response is expected_response
    active_subscription.assert_awaited_once_with(context.session, 42)
    run_payment.assert_awaited_once_with(tribute_service._SHOP_DESCRIPTOR, context)


@pytest.mark.parametrize(
    "effect_kwargs",
    [
        {"promo_bonus_days": 7},
        {"promo_duration_multiplier": 2.0},
        {"promo_traffic_multiplier": 1.5},
    ],
)
def test_shop_webapp_rejects_non_price_recurring_promo_effects(
    monkeypatch,
    effect_kwargs: dict[str, object],
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock(return_value=None)
    run_payment = AsyncMock()
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=1,
        price=149.0,
        stars_price=None,
        description="Unsupported recurring promo effect",
        sale_mode="subscription@pro",
        promo_code_id=7,
        **effect_kwargs,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response.status == 400
    assert _response_json(response)["error"] == "payment_unavailable"
    active_subscription.assert_awaited_once_with(context.session, 42)
    run_payment.assert_not_awaited()


def test_shop_webapp_rejects_subscription_with_one_time_hwid_purchase(monkeypatch) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock(return_value=None)
    run_payment = AsyncMock()
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=1,
        price=249.0,
        stars_price=None,
        description="Recurring subscription with one-time HWID device",
        sale_mode="subscription@pro",
        hwid_device_count=1,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response.status == 400
    assert _response_json(response)["error"] == "payment_unavailable"
    active_subscription.assert_awaited_once_with(context.session, 42)
    run_payment.assert_not_awaited()


def test_shop_webapp_allows_one_time_topup_with_promo(monkeypatch) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock()
    expected_response = object()
    run_payment = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=10,
        price=99.0,
        stars_price=None,
        description="Discounted one-time traffic topup",
        sale_mode="topup@pro",
        promo_code_id=7,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response is expected_response
    active_subscription.assert_not_awaited()
    run_payment.assert_awaited_once_with(tribute_service._SHOP_DESCRIPTOR, context)


def test_shop_webapp_allows_separate_one_time_hwid_purchase(monkeypatch) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock()
    expected_response = object()
    run_payment = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=1,
        price=149.0,
        stars_price=None,
        description="One-time HWID device",
        sale_mode="hwid_devices@pro",
        hwid_device_count=1,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response is expected_response
    active_subscription.assert_not_awaited()
    run_payment.assert_awaited_once_with(tribute_service._SHOP_DESCRIPTOR, context)


@pytest.mark.parametrize(
    "sale_mode",
    ["subscription@pro", "tariff_upgrade@pro"],
)
def test_shop_webapp_blocks_new_subscription_like_purchase_during_active_recurrence(
    monkeypatch,
    sale_mode: str,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock(
        return_value=SimpleNamespace(
            subscription_id=501,
            tariff_key="pro",
            provider="tribute",
            auto_renew_enabled=True,
        )
    )
    run_payment = AsyncMock()
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=1,
        price=199.0,
        stars_price=None,
        description="Duplicate recurring purchase",
        sale_mode=sale_mode,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response.status == 400
    assert _response_json(response)["error"] == "payment_unavailable"
    active_subscription.assert_awaited_once_with(context.session, 42)
    run_payment.assert_not_awaited()


def test_shop_webapp_allows_topup_during_active_recurrence(monkeypatch) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    active_subscription = AsyncMock()
    expected_response = object()
    run_payment = AsyncMock(return_value=expected_response)
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(tribute_service, "run_webapp_payment", run_payment)
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=10,
        price=149.0,
        stars_price=None,
        description="Traffic topup",
        sale_mode="topup@pro",
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response is expected_response
    active_subscription.assert_not_awaited()
    run_payment.assert_awaited_once_with(tribute_service._SHOP_DESCRIPTOR, context)


@pytest.mark.parametrize(
    "sale_mode",
    ["subscription@pro", "tariff_upgrade@pro"],
)
def test_generic_webapp_blocks_subscription_replacement_during_tribute_recurrence(
    monkeypatch,
    sale_mode: str,
) -> None:
    session = SimpleNamespace()
    active_subscription = AsyncMock(
        return_value=SimpleNamespace(
            provider="TRIBUTE",
            auto_renew_enabled=True,
        )
    )
    monkeypatch.setattr(billing_payments, "get_settings", lambda _request: SimpleNamespace())
    monkeypatch.setattr(
        billing_payments.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )

    response = asyncio.run(
        billing_payments._create_subscription_payment(
            request=cast(Any, SimpleNamespace(app={})),
            session=cast(Any, session),
            user_id=42,
            method="tribute",
            months=1,
            price=149.0,
            stars_price=None,
            currency="RUB",
            lang="en",
            sale_mode=sale_mode,
        )
    )

    assert response.status == 409
    assert _response_json(response)["error"] == "tribute_recurring_conflict"
    active_subscription.assert_awaited_once_with(session, 42)


def test_generic_webapp_allows_topup_during_tribute_recurrence(monkeypatch) -> None:
    import bot.payment_providers as payment_providers

    settings = SimpleNamespace()
    request = SimpleNamespace(app={})
    session = SimpleNamespace()
    active_subscription = AsyncMock(
        return_value=SimpleNamespace(
            subscription_id=501,
            tariff_key="pro",
            provider="tribute",
            auto_renew_enabled=True,
        )
    )
    expected_response = object()
    create_payment = AsyncMock(return_value=expected_response)
    provider_spec = SimpleNamespace(
        create_webapp_payment=create_payment,
        reuse_webapp_payment=None,
        is_visible_for_user=lambda *_args, **_kwargs: True,
        is_usable_for_payment_currency=lambda *_args, **_kwargs: True,
        is_usable_for_payment_amount=lambda *_args, **_kwargs: True,
        is_usable_for_payment_context=lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(billing_payments, "get_settings", lambda _request: settings)
    monkeypatch.setattr(billing_payments, "get_i18n", lambda _request: None)
    monkeypatch.setattr(
        billing_payments,
        "_localized_payment_description",
        lambda **_kwargs: "Traffic topup",
    )
    monkeypatch.setattr(
        billing_payments.subscription_dal,
        "get_active_subscription_by_user_id",
        active_subscription,
    )
    monkeypatch.setattr(
        payment_providers,
        "get_provider_spec",
        lambda _method: provider_spec,
    )

    response = asyncio.run(
        billing_payments._create_subscription_payment(
            request=cast(Any, request),
            session=cast(Any, session),
            user_id=42,
            method="tribute",
            months=10,
            price=99.0,
            stars_price=None,
            currency="RUB",
            lang="en",
            sale_mode="topup@pro",
            traffic_gb=10.0,
            promo_code_id=7,
        )
    )

    assert response is expected_response
    active_subscription.assert_awaited_once_with(session, 42)
    create_payment.assert_awaited_once()
    assert create_payment.await_args is not None
    context = create_payment.await_args.args[0]
    assert context.sale_mode == "topup@pro"
    assert context.promo_code_id == 7
    assert context.entitlement_context_snapshot is not None


@pytest.mark.parametrize(
    ("sale_mode", "months"),
    [
        ("subscription", 1),
        ("subscription@missing", 1),
        ("subscription@pro", 6),
        ("traffic_package@pro", 1),
    ],
)
def test_checkout_rejects_missing_or_unmapped_plan_context(
    monkeypatch,
    sale_mode: str,
    months: int,
) -> None:
    monkeypatch.setattr(
        tribute_service.subscription_dal,
        "get_active_subscription_by_user_id",
        AsyncMock(return_value=None),
    )
    service = _service()
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=months,
        price=100.0,
        stars_price=None,
        description="Plan",
        sale_mode=sale_mode,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert response.status == 400
    assert _response_json(response)["error"] == "payment_unavailable"


@pytest.mark.parametrize(
    ("sale_mode", "units", "expected_product_id", "expected_link"),
    [
        (
            "traffic_package@traffic",
            50,
            501,
            "https://t.me/tribute/app?startapp=p501",
        ),
        (
            "topup@pro",
            10,
            502,
            "https://web.tribute.tg/p/502",
        ),
        (
            "premium_topup@pro",
            5,
            503,
            "https://t.me/tribute/app?startapp=p503",
        ),
    ],
)
def test_digital_product_checkout_uses_fixed_configured_traffic_link(
    sale_mode: str,
    units: int,
    expected_product_id: int,
    expected_link: str,
) -> None:
    product = lambda product_id, link: SimpleNamespace(product_id=product_id, link=link)
    traffic_tariff = _tariff(
        key="traffic",
        billing_model="traffic",
        traffic_products={
            "50": product(501, "https://t.me/tribute/app?startapp=p501"),
        },
    )
    period_tariff = _tariff(
        key="pro",
        traffic_products={
            "10": product(502, "https://web.tribute.tg/p/502"),
        },
        premium_traffic_products={
            "5": product(503, "https://t.me/tribute/app?startapp=p503"),
        },
    )
    service = _service(settings=_settings(traffic_tariff, period_tariff))
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=units,
        price=0.01,
        stars_price=None,
        description="The fixed Tribute product owns the checkout price",
        sale_mode=sale_mode,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert tribute_service.tribute_supports_checkout(
        service.settings,
        units,
        sale_mode,
    )
    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "action": "open_link",
        "payment_url": expected_link,
        "payment_id": None,
    }
    binding = tribute_service._binding_for_checkout(
        service.settings,
        sale_mode=sale_mode,
        months=units,
    )
    assert binding is not None
    assert binding.product_id == expected_product_id


@pytest.mark.parametrize(
    ("sale_mode", "units"),
    [
        ("traffic_package@traffic", 51),
        ("topup@pro", 11),
        ("premium_topup@pro", 6),
        ("hwid_devices@pro", 1),
    ],
)
def test_digital_product_checkout_rejects_unmapped_or_non_traffic_context(
    sale_mode: str,
    units: int,
) -> None:
    product = lambda product_id, link: SimpleNamespace(product_id=product_id, link=link)
    service = _service(
        settings=_settings(
            _tariff(
                key="traffic",
                billing_model="traffic",
                traffic_products={
                    "50": product(501, "https://t.me/tribute/app?startapp=p501"),
                },
            ),
            _tariff(
                key="pro",
                traffic_products={
                    "10": product(502, "https://web.tribute.tg/p/502"),
                },
                premium_traffic_products={
                    "5": product(503, "https://t.me/tribute/app?startapp=p503"),
                },
            ),
        )
    )
    context = WebAppPaymentContext(
        request=SimpleNamespace(app={TRIBUTE_SERVICE_KEY: service}),
        session=SimpleNamespace(),
        user_id=42,
        method="tribute",
        months=units,
        price=100,
        stars_price=None,
        description="Unmapped product",
        sale_mode=sale_mode,
    )

    response = asyncio.run(tribute_service.create_webapp_payment(context))

    assert not tribute_service.tribute_supports_checkout(
        service.settings,
        units,
        sale_mode,
    )
    assert response.status == 400
    assert _response_json(response)["error"] == "payment_unavailable"


def test_webhook_new_subscription_uses_exact_provider_expiry(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(price=1234, amount=987)
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    event = _event()
    payment = _payment()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=None,
        payment=payment,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    request = mocks.finalize.await_args.args[0]
    assert request.amount == 12.34
    assert request.currency == "RUB"
    assert request.months == 1
    assert request.skip_referral_bonus is False
    assert request.activation_extra_kwargs == {"authoritative_end_at": EXPIRES_AT}
    mocks.enable.assert_awaited_once_with(session, user_id=42, tariff_key="pro")
    assert event.status == "processed"
    assert event.payment_id == 55


def test_webhook_renewal_updates_the_existing_entitlement(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    expires_at = EXPIRES_AT + timedelta(days=31)
    payload = _payload(expires_at=expires_at)
    envelope = _envelope(
        "renewed_subscription",
        payload,
        created_at=CREATED_AT + timedelta(days=31),
    )
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    entitlement = _entitlement()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event(),
        entitlement=entitlement,
        payment=_payment(),
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert entitlement.active_until == expires_at
    assert entitlement.last_event_name == "renewed_subscription"
    assert entitlement.last_event_fingerprint == fingerprint
    request = mocks.finalize.await_args.args[0]
    assert request.activation_extra_kwargs["authoritative_end_at"] == expires_at
    mocks.enable.assert_awaited_once()


@pytest.mark.parametrize(
    ("subscription_type", "period_id", "price"),
    [
        ("trial", 999, 0),
        ("gift", 201, 1234),
    ],
)
def test_trial_and_gift_skip_referral_rewards(
    monkeypatch,
    subscription_type: str,
    period_id: int,
    price: int,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(
        subscription_type=subscription_type,
        period_id=period_id,
        price=price,
    )
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event(),
        entitlement=None,
        payment=_payment(),
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    request = mocks.finalize.await_args.args[0]
    assert request.skip_referral_bonus is True
    assert request.activation_extra_kwargs["authoritative_end_at"] == EXPIRES_AT


def test_payment_records_gross_price_not_creator_net_amount(monkeypatch) -> None:
    session = _FakeSession()
    payload = _payload(price=1234, amount=987)
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    ensure_payment = AsyncMock(return_value=_payment())
    monkeypatch.setattr(
        tribute_service.payment_dal,
        "ensure_payment_with_provider_id",
        ensure_payment,
    )
    event = _event()

    payment = asyncio.run(
        TributeService._ensure_payment(
            session,
            event=event,
            envelope=envelope,
            payload=payload,
            binding=TributePlanBinding(
                tariff_key="pro",
                months=1,
                link="https://t.me/tribute/app?startapp=subscription",
                subscription_id=101,
                period_id=201,
            ),
            fingerprint=fingerprint,
            user_id=4242,
        )
    )

    assert payment.payment_id == 55
    ensure_payment_call = ensure_payment.await_args
    assert ensure_payment_call is not None
    # The payment belongs to the local account, not to the Telegram ID.
    assert ensure_payment_call.kwargs["user_id"] == 4242
    assert ensure_payment_call.kwargs["amount"] == 12.34
    assert ensure_payment_call.kwargs["amount"] != 9.87
    assert ensure_payment_call.kwargs["provider_payment_id"] == fingerprint
    assert ensure_payment_call.kwargs["sale_mode"] == "subscription@pro"
    assert event.payment_id == 55


def test_duplicate_processed_event_does_not_activate_again(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload()
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event("processed"),
        entitlement=None,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "processed",
        "duplicate": True,
    }
    mocks.get_entitlement.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_creator_second_active_recurrence_is_recorded_for_manual_review(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload()
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    event = _event()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=None,
    )
    mocks.active_creator_subscription.return_value = 999

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "ignored",
        "manual_review": True,
    }
    mocks.user.assert_awaited_once_with(session, 42)
    mocks.active_creator_subscription.assert_awaited_once_with(
        session,
        user_id=42,
        exclude_subscription_id=101,
    )
    assert event.status == "ignored"
    assert event.status_reason == "duplicate_active_recurrence_manual_review"
    mocks.create_entitlement.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize("event_name", ["new_subscription", "renewed_subscription"])
def test_creator_subscription_binds_to_the_local_account_not_the_telegram_id(
    monkeypatch,
    event_name: str,
) -> None:
    """Tribute speaks Telegram IDs; everything local is keyed on User.user_id."""

    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(telegram_user_id=42)
    envelope = _envelope(event_name, payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    entitlement = (
        _entitlement(last_event_name="new_subscription")
        if event_name == "renewed_subscription"
        else None
    )
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event(),
        entitlement=entitlement,
        user=SimpleNamespace(user_id=7777, telegram_id=42),
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    mocks.user_by_telegram.assert_awaited_once_with(session, 42)
    mocks.user.assert_awaited_once_with(session, 7777)
    assert mocks.ensure_payment.await_args.kwargs["user_id"] == 7777
    assert mocks.finalize.await_args.args[0].user_id == 7777
    # Both duplicate-recurrence probes ask about the same identity.
    assert mocks.active_shop_order.await_args.kwargs["user_id"] == 7777
    assert mocks.active_creator_subscription.await_args.kwargs["user_id"] == 7777


def test_creator_subscription_falls_back_to_the_primary_key_for_imported_rows(
    monkeypatch,
) -> None:
    """Rows imported from another bot carry the Telegram ID as their user_id."""

    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(telegram_user_id=42)
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event(),
        entitlement=None,
        user=SimpleNamespace(user_id=42, telegram_id=None),
    )
    mocks.user_by_telegram.return_value = None
    by_primary_key = AsyncMock(return_value=SimpleNamespace(user_id=42, telegram_id=None))
    monkeypatch.setattr(tribute_service.user_dal, "get_user_by_id", by_primary_key)

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    by_primary_key.assert_awaited_once_with(session, 42)
    mocks.user.assert_awaited_once_with(session, 42)
    assert mocks.ensure_payment.await_args.kwargs["user_id"] == 42


def test_creator_recurrence_sees_a_shop_recurrence_of_the_same_local_account(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(telegram_user_id=42)
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    event = _event()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=None,
        user=SimpleNamespace(user_id=7777, telegram_id=42),
    )
    # The Shop order was written against the local account, so the Creator
    # side only finds it when it asks with the same identity.
    mocks.active_shop_order.return_value = SHOP_ORDER_UUID

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response)["manual_review"] is True
    assert event.status_reason == "duplicate_active_recurrence_manual_review"
    assert mocks.active_shop_order.await_args.kwargs["user_id"] == 7777
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_processing_event_resumes_after_payment_was_already_finalized(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload()
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    entitlement = _entitlement(
        last_event_name="new_subscription",
        last_event_created_at=CREATED_AT,
        last_event_fingerprint=fingerprint,
    )
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event("processing"),
        entitlement=entitlement,
        payment=_payment("succeeded"),
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    mocks.enable.assert_awaited_once()


def test_cancellation_disables_renewal_without_shortening_paid_access(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    paid_until = EXPIRES_AT + timedelta(days=5)
    payload = _payload(expires_at=EXPIRES_AT)
    envelope = _envelope(
        "cancelled_subscription",
        payload,
        created_at=CREATED_AT + timedelta(days=1),
    )
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    entitlement = _entitlement(active_until=paid_until)
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=_event(),
        entitlement=entitlement,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response)["status"] == "pre_cancelled"
    assert entitlement.status == "pre_cancelled"
    assert entitlement.active_until == paid_until
    mocks.disable.assert_awaited_once_with(session, user_id=42, tariff_key="pro")
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize("event_name", ["new_subscription", "renewed_subscription"])
def test_delayed_positive_after_cancellation_grants_paid_period_without_reactivation(
    monkeypatch,
    event_name: str,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(expires_at=EXPIRES_AT)
    envelope = _envelope(event_name, payload, created_at=CREATED_AT)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    cancellation_created_at = CREATED_AT + timedelta(seconds=1)
    entitlement = _entitlement(
        last_event_name="cancelled_subscription",
        last_event_created_at=cancellation_created_at,
        last_event_fingerprint="cancellation-fingerprint",
        status="pre_cancelled",
        active_until=EXPIRES_AT,
    )
    event = _event()
    payment = _payment()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=entitlement,
        payment=payment,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "processed",
        "payment_id": 55,
        "expires_at": EXPIRES_AT.isoformat(timespec="microseconds"),
        "recurrence_status": "pre_cancelled",
    }
    request = mocks.finalize.await_args.args[0]
    assert request.activation_extra_kwargs == {"authoritative_end_at": EXPIRES_AT}
    assert entitlement.status == "pre_cancelled"
    assert entitlement.last_event_name == "cancelled_subscription"
    assert entitlement.last_event_created_at == cancellation_created_at
    assert entitlement.last_event_fingerprint == "cancellation-fingerprint"
    mocks.enable.assert_not_awaited()
    mocks.disable.assert_awaited_once_with(session, user_id=42, tariff_key="pro")
    assert event.status == "processed"
    assert event.status_reason == "paid_period_after_cancellation"
    assert event.payment_id == 55

    replay = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert replay.status == 200
    assert _response_json(replay) == {
        "ok": True,
        "status": "processed",
        "duplicate": True,
    }
    assert mocks.finalize.await_count == 1
    assert mocks.disable.await_count == 1


def test_delayed_positive_after_cancellation_retries_transient_activation_failure(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload()
    envelope = _envelope("new_subscription", payload, created_at=CREATED_AT)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    entitlement = _entitlement(
        last_event_name="cancelled_subscription",
        last_event_created_at=CREATED_AT + timedelta(seconds=1),
        last_event_fingerprint="cancellation-fingerprint",
        status="pre_cancelled",
        active_until=EXPIRES_AT,
    )
    event = _event()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=entitlement,
        payment=_payment(),
    )
    mocks.finalize.return_value = None

    failed = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert failed.status == 500
    assert _response_json(failed) == {"ok": False, "error": "activation_failed"}
    assert event.status == "processing"
    assert entitlement.status == "pre_cancelled"
    assert entitlement.last_event_name == "cancelled_subscription"
    mocks.enable.assert_not_awaited()
    mocks.disable.assert_not_awaited()

    mocks.finalize.return_value = SimpleNamespace()
    retried = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert retried.status == 200
    assert _response_json(retried)["recurrence_status"] == "pre_cancelled"
    assert mocks.finalize.await_count == 2
    mocks.enable.assert_not_awaited()
    mocks.disable.assert_awaited_once_with(session, user_id=42, tariff_key="pro")
    assert event.status == "processed"


@pytest.mark.parametrize(
    ("event_name", "subscription_type", "price", "expected_skip_referral"),
    [
        ("new_subscription", "trial", 0, True),
        ("renewed_subscription", "regular", 1234, False),
    ],
)
def test_delayed_positive_after_newer_positive_records_payment_without_rewinding_state(
    monkeypatch,
    event_name: str,
    subscription_type: str,
    price: int,
    expected_skip_referral: bool,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload(
        subscription_type=subscription_type,
        price=price,
        expires_at=EXPIRES_AT,
    )
    envelope = _envelope(event_name, payload, created_at=CREATED_AT)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    newer_created_at = CREATED_AT + timedelta(days=31)
    newer_expires_at = EXPIRES_AT + timedelta(days=31)
    entitlement = _entitlement(
        last_event_name="renewed_subscription",
        last_event_created_at=newer_created_at,
        last_event_fingerprint="newer-renewal-fingerprint",
        status="active",
        active_until=newer_expires_at,
    )
    event = _event()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=entitlement,
        payment=_payment(),
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "processed",
        "payment_id": 55,
        "expires_at": EXPIRES_AT.isoformat(timespec="microseconds"),
        "recurrence_status": "active",
    }
    request = mocks.finalize.await_args.args[0]
    assert request.activation_extra_kwargs == {"authoritative_end_at": EXPIRES_AT}
    assert request.skip_referral_bonus is expected_skip_referral
    ensure_payment_call = mocks.ensure_payment.await_args
    assert ensure_payment_call is not None
    assert ensure_payment_call.kwargs["fingerprint"] == fingerprint
    assert entitlement.status == "active"
    assert entitlement.active_until == newer_expires_at
    assert entitlement.last_event_name == "renewed_subscription"
    assert entitlement.last_event_created_at == newer_created_at
    assert entitlement.last_event_fingerprint == "newer-renewal-fingerprint"
    mocks.enable.assert_awaited_once_with(session, user_id=42, tariff_key="pro")
    mocks.disable.assert_not_awaited()
    assert event.status == "processed"
    assert event.status_reason == "paid_period_after_newer_positive"
    assert event.payment_id == 55

    replay = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert replay.status == 200
    assert _response_json(replay) == {
        "ok": True,
        "status": "processed",
        "duplicate": True,
    }
    assert mocks.ensure_payment.await_count == 1
    assert mocks.finalize.await_count == 1
    assert mocks.enable.await_count == 1


def test_delayed_positive_after_newer_positive_retries_transient_activation_failure(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload()
    envelope = _envelope("renewed_subscription", payload, created_at=CREATED_AT)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    newer_created_at = CREATED_AT + timedelta(days=31)
    entitlement = _entitlement(
        last_event_name="renewed_subscription",
        last_event_created_at=newer_created_at,
        last_event_fingerprint="newer-renewal-fingerprint",
        status="active",
        active_until=EXPIRES_AT + timedelta(days=31),
    )
    event = _event()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=entitlement,
        payment=_payment(),
    )
    mocks.finalize.return_value = None

    failed = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert failed.status == 500
    assert _response_json(failed) == {"ok": False, "error": "activation_failed"}
    assert event.status == "processing"
    assert entitlement.status == "active"
    assert entitlement.last_event_created_at == newer_created_at
    mocks.enable.assert_not_awaited()
    mocks.disable.assert_not_awaited()

    mocks.finalize.return_value = SimpleNamespace()
    retried = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert retried.status == 200
    assert _response_json(retried)["recurrence_status"] == "active"
    assert mocks.ensure_payment.await_count == 2
    assert mocks.finalize.await_count == 2
    mocks.enable.assert_awaited_once_with(session, user_id=42, tariff_key="pro")
    mocks.disable.assert_not_awaited()
    assert entitlement.status == "active"
    assert entitlement.last_event_created_at == newer_created_at
    assert event.status == "processed"


@pytest.mark.parametrize(
    ("incoming_name", "incoming_created_at", "current_name", "current_created_at"),
    [
        (
            "cancelled_subscription",
            CREATED_AT - timedelta(seconds=1),
            "renewed_subscription",
            CREATED_AT,
        ),
        (
            "new_subscription",
            CREATED_AT,
            "cancelled_subscription",
            CREATED_AT,
        ),
    ],
)
def test_stale_or_out_of_order_events_are_ignored(
    monkeypatch,
    incoming_name: str,
    incoming_created_at: datetime,
    current_name: str,
    current_created_at: datetime,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payload = _payload()
    envelope = _envelope(
        incoming_name,
        payload,
        created_at=incoming_created_at,
    )
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    event = _event()
    entitlement = _entitlement(
        last_event_name=current_name,
        last_event_created_at=current_created_at,
    )
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=entitlement,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response)["status"] == "ignored"
    assert event.status == "ignored"
    assert event.status_reason == "stale_event"
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    mocks.enable.assert_not_awaited()
    mocks.disable.assert_not_awaited()


def test_unknown_user_is_retryable_and_does_not_claim_event(monkeypatch) -> None:
    service = _service()
    payload = _payload(telegram_user_id=404)
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    ensure_event = AsyncMock(
        side_effect=AssertionError("unknown user must not claim a durable event")
    )
    monkeypatch.setattr(
        tribute_service.user_dal,
        "get_user_by_telegram_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        tribute_service.user_dal,
        "get_user_by_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        tribute_service.user_dal,
        "lock_user_by_id",
        AsyncMock(side_effect=AssertionError("an unknown Telegram ID must not be locked")),
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "ensure_webhook_event",
        ensure_event,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 404
    assert _response_json(response)["error"] == "user_not_found"
    ensure_event.assert_not_awaited()


def test_unknown_plan_is_acknowledged_without_granting_access(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(
        settings=SimpleNamespace(tariffs_config=_TariffsConfig([])),
        session=session,
    )
    payload = _payload()
    envelope = _envelope("new_subscription", payload)
    fingerprint = tribute_service._event_fingerprint(envelope, payload)
    event = _event()
    mocks = _install_event_mocks(
        monkeypatch,
        service,
        event=event,
        entitlement=None,
    )

    response = asyncio.run(service._process_subscription_event(envelope, payload, fingerprint))

    assert response.status == 200
    assert _response_json(response)["status"] == "ignored"
    assert event.status == "ignored"
    assert event.status_reason == "unknown_plan"
    mocks.create_entitlement.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("product_id", "sale_mode", "tariff_key", "units"),
    [
        (501, "traffic_package@traffic", "traffic", 50.0),
        (502, "topup@pro", "pro", 10.0),
        (503, "premium_topup@pro", "pro", 5.0),
    ],
)
def test_digital_product_success_uses_immutable_configured_traffic_sku(
    monkeypatch,
    product_id: int,
    sale_mode: str,
    tariff_key: str,
    units: float,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    payment = _digital_payment(
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        purchased_gb=units,
    )
    purchase = _product_purchase(
        product_id=product_id,
        sale_mode=sale_mode,
        tariff_key=tariff_key,
        units=units,
    )
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=payment,
    )
    provider_payload = _digital_product_payload(
        product_id=product_id,
        amount=14900,
    )
    provider_payload["product_name"] = "Untrusted name: 9999 GB and another tariff"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("new_digital_product", provider_payload),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    payment_values = mocks.ensure_payment.await_args.kwargs
    assert payment_values["provider"] == "tribute"
    assert payment_values["provider_payment_id"] == "digital_product:7001"
    assert payment_values["amount"] == 149.0
    assert payment_values["currency"] == "RUB"
    assert payment_values["sale_mode"] == sale_mode
    assert payment_values["tariff_key"] == tariff_key
    assert payment_values["purchased_gb"] == units
    assert payment_values.get("purchased_hwid_devices") is None
    success_request = mocks.finalize.await_args.args[0]
    assert success_request.payment is payment
    assert success_request.sale_mode == sale_mode
    assert success_request.traffic_amount == units
    assert success_request.skip_referral_bonus is True
    assert "authoritative_end_at" not in success_request.activation_extra_kwargs
    assert purchase.status == "fulfilled"
    assert purchase.payment_id == payment.payment_id
    assert purchase.fulfilled_at is not None


def test_digital_product_binds_to_the_local_account_not_the_telegram_id(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(user_id=7777)
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        user=SimpleNamespace(user_id=7777, telegram_id=42),
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("new_digital_product", _digital_product_payload()),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    mocks.user_by_telegram.assert_awaited_once_with(session, 42)
    mocks.user.assert_awaited_once_with(session, 7777)
    assert mocks.ensure_purchase.await_args.args[1]["user_id"] == 7777
    assert mocks.ensure_purchase.await_args.args[1]["telegram_user_id"] == 42
    assert mocks.ensure_payment.await_args.kwargs["user_id"] == 7777
    assert mocks.finalize.await_args.args[0].user_id == 7777


def test_digital_product_cross_tariff_topup_is_quarantined(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(
        product_id=502,
        sale_mode="topup@pro",
        tariff_key="pro",
        units=10,
    )
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=91,
        tariff_key="other",
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(product_id=502),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "reason": "active_tariff_mismatch",
    }
    assert purchase.status == "quarantined"
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_digital_product_retry_rejects_replaced_same_tariff_subscription(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    snapshot = build_entitlement_context_snapshot(
        sale_mode="topup@pro",
        active_subscription=SimpleNamespace(subscription_id=91, tariff_key="pro"),
    )
    payment = _digital_payment(
        sale_mode="topup@pro",
        tariff_key="pro",
        purchased_gb=10,
        entitlement_context_snapshot=snapshot,
    )
    purchase = _product_purchase(
        status="processing",
        product_id=502,
        sale_mode="topup@pro",
        tariff_key="pro",
        units=10,
        payment_id=payment.payment_id,
    )
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=payment,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=92,
        tariff_key="pro",
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(product_id=502),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["reason"] == "active_subscription_changed"
    mocks.update_payment_status.assert_awaited_once_with(
        session,
        payment.payment_id,
        "activation_failed",
    )
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_digital_product_duplicate_fulfilled_purchase_does_not_grant_twice(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(status="fulfilled", payment_id=75)
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=_digital_payment(status="succeeded"),
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["duplicate"] is True
    mocks.ensure_payment.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_digital_product_processing_retry_resumes_from_succeeded_payment(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(status="processing", payment_id=75)
    payment = _digital_payment(status="succeeded")
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=payment,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(),
                sent_at=CREATED_AT + timedelta(hours=8),
            ),
        )
    )

    assert response.status == 200
    assert purchase.status == "fulfilled"
    assert purchase.payment_id == 75
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("fresh_status", "expected_status"),
    [
        ("succeeded", 200),
        ("processing", 503),
    ],
)
def test_digital_product_concurrent_claim_observes_fresh_payment_state(
    monkeypatch,
    fresh_status: str,
    expected_status: int,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(status="processing")
    pending_payment = _digital_payment(status="pending_tribute")
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=pending_payment,
    )
    mocks.claim.return_value = None
    mocks.get_payment.return_value = _digital_payment(status=fresh_status)

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(),
            ),
        )
    )

    assert response.status == expected_status
    mocks.finalize.assert_not_awaited()
    if expected_status == 200:
        assert purchase.status == "fulfilled"
    else:
        assert purchase.status == "processing"


def test_digital_product_unknown_product_is_acknowledged_without_purchase(
    monkeypatch,
) -> None:
    service = _service(settings=_digital_settings())
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=_product_purchase(product_id=999),
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(product_id=999),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "ignored"
    mocks.ensure_purchase.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_digital_product_missing_telegram_identity_is_ignored(monkeypatch) -> None:
    service = _service(settings=_digital_settings())
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=_product_purchase(telegram_user_id=None, user_id=None),
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(
                    telegram_user_id=None,
                    trb_user_id="W-15408",
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "ignored"
    mocks.user.assert_not_awaited()
    mocks.ensure_purchase.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()


def test_digital_product_unknown_local_user_is_retryable(monkeypatch) -> None:
    service = _service(settings=_digital_settings())
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=_product_purchase(),
    )
    mocks.user.return_value = None

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(),
            ),
        )
    )

    assert response.status == 404
    assert _response_json(response)["error"] == "user_not_found"
    mocks.ensure_purchase.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()


def test_digital_product_refund_before_success_creates_blocking_tombstone(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    tombstone = _product_purchase(
        status="refunded",
        sale_mode=None,
        tariff_key=None,
        units=None,
        payment_id=None,
    )
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=tombstone,
    )

    refund_response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "digital_product_refunded",
                _digital_refund_payload(),
            ),
        )
    )
    success_response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "new_digital_product",
                _digital_product_payload(),
                created_at=CREATED_AT + timedelta(seconds=1),
            ),
        )
    )

    assert refund_response.status == 200
    assert tombstone.status == "refunded"
    assert tombstone.refunded_at == EXPIRES_AT
    assert success_response.status == 200
    assert _response_json(success_response)["status"] == "ignored"
    mocks.ensure_payment.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_fulfilled_digital_product_refund_marks_records_without_traffic_clawback(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(status="fulfilled", payment_id=75)
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=_digital_payment(status="succeeded"),
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "digital_product_refunded",
                _digital_refund_payload(),
            ),
        )
    )

    assert response.status == 200
    assert purchase.status == "refunded"
    assert purchase.refunded_at == EXPIRES_AT
    assert purchase.refund_reason == "customer_request"
    mocks.update_payment_status.assert_awaited_once_with(session, 75, "refunded")
    mocks.ensure_payment.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("product_id", 999),
        ("transaction_id", 9999),
        ("telegram_user_id", 777),
    ],
)
def test_digital_product_mismatched_immutable_ids_are_quarantined(
    monkeypatch,
    field: str,
    value: int,
) -> None:
    session = _FakeSession()
    service = _service(settings=_digital_settings(), session=session)
    purchase = _product_purchase(status="fulfilled", payment_id=75)
    mocks = _install_product_mocks(
        monkeypatch,
        service,
        purchase=purchase,
        payment=_digital_payment(status="succeeded"),
    )
    refund = _digital_refund_payload()
    refund[field] = value

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("digital_product_refunded", refund),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "quarantined"
    assert purchase.status == "fulfilled"
    assert purchase.payment_id == 75
    mocks.update_payment_status.assert_not_awaited()
    mocks.ensure_payment.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("amount", "expected_minor"),
    [
        (Decimal("1.00"), 100),
        (Decimal("3000.00"), 300_000),
    ],
)
def test_shop_order_amount_accepts_documented_boundaries(
    amount: Decimal,
    expected_minor: int,
) -> None:
    assert tribute_shop_major_to_minor(amount, "rub") == expected_minor


@pytest.mark.parametrize("amount", [Decimal("0.99"), Decimal("3000.01")])
def test_shop_order_amount_rejects_values_outside_documented_boundaries(
    amount: Decimal,
) -> None:
    with pytest.raises(ValueError):
        tribute_shop_major_to_minor(amount, "rub")


@pytest.mark.parametrize(
    ("sale_mode", "months", "expected_period"),
    [
        ("traffic_package@traffic", 50, "onetime"),
        ("topup@pro", 10, "onetime"),
        ("premium_topup@pro", 5, "onetime"),
        ("hwid_devices@pro", 1, "onetime"),
        ("tariff_upgrade@pro", 1, "onetime"),
        ("subscription@pro", 1, "monthly"),
        ("subscription@pro", 3, "quarterly"),
        ("subscription@pro", 6, "halfyearly"),
        ("subscription@pro", 12, "yearly"),
    ],
)
def test_create_shop_order_posts_dynamic_order_with_local_payment_correlation(
    monkeypatch,
    sale_mode: str,
    months: int,
    expected_period: str,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    http_session = object()
    get_session = AsyncMock(return_value=http_session)
    post = AsyncMock(
        return_value=(
            True,
            _shop_order_response(
                amount=14925,
                period=expected_period,
            ),
        )
    )
    monkeypatch.setattr(service, "_get_session", get_session)
    monkeypatch.setattr(tribute_service, "post_json_request", post)

    success, result = asyncio.run(
        service.create_shop_order(
            payment_db_id=85,
            user_id=42,
            amount=149.25,
            currency="RUB",
            title="  Remnawave purchase  ",
            description="  Stored payment snapshot  ",
            months=months,
            sale_mode=sale_mode,
        )
    )

    assert success is True
    assert result == _shop_order_response(
        amount=14925,
        period=expected_period,
    )
    get_session.assert_awaited_once_with()
    post.assert_awaited_once()
    call = post.await_args
    assert call is not None
    assert call.args == (
        http_session,
        "https://tribute.tg/api/v1/shop/orders",
    )
    assert call.kwargs["headers"] == {"Api-Key": API_KEY}
    assert call.kwargs["body"] == {
        "shopId": SHOP_ID,
        "amount": 14925,
        "currency": "rub",
        "title": "Remnawave purchase",
        "description": "Stored payment snapshot",
        "customerId": "telegram:42",
        "comment": "minishop-payment:85",
        "period": expected_period,
    }


def test_create_recurring_shop_order_uses_regular_and_discounted_first_period_amount(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    post = AsyncMock(
        return_value=(
            True,
            _shop_order_response(
                amount=19900,
                period="monthly",
                first_period_amount=14900,
            ),
        )
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(tribute_service, "post_json_request", post)

    success, result = asyncio.run(
        service.create_shop_order(
            payment_db_id=85,
            user_id=42,
            amount=149.0,
            regular_amount=199.0,
            currency="RUB",
            title="Discounted first cycle",
            description="Stored promo snapshot",
            months=1,
            sale_mode="subscription@pro",
        )
    )

    assert success is True
    assert result["amount"] == 19900
    assert result["firstPeriodAmount"] == 14900
    post_args = post.await_args
    assert post_args is not None
    assert post_args.kwargs["body"]["amount"] == 19900
    assert post_args.kwargs["body"]["firstPeriodAmount"] == 14900


def test_create_recurring_shop_order_rejects_missing_first_period_response_snapshot(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        tribute_service,
        "post_json_request",
        AsyncMock(
            return_value=(
                True,
                _shop_order_response(
                    amount=19900,
                    period="monthly",
                ),
            )
        ),
    )

    success, result = asyncio.run(
        service.create_shop_order(
            payment_db_id=85,
            user_id=42,
            amount=149.0,
            regular_amount=199.0,
            currency="RUB",
            title="Discounted first cycle",
            description="Stored promo snapshot",
            months=1,
            sale_mode="subscription@pro",
        )
    )

    assert success is False
    assert result == {
        "message": "invalid_shop_response",
        "detail": "first_period_amount_mismatch",
    }


def test_shop_create_adapter_uses_persisted_checkout_base_as_regular_amount() -> None:
    service = SimpleNamespace(create_shop_order=AsyncMock(return_value=(True, {})))
    request = SimpleNamespace(
        payment=SimpleNamespace(
            payment_id=85,
            checkout_base_amount=199.0,
        ),
        user_id=42,
        amount=149.0,
        currency="RUB",
        description="Discounted first cycle",
        months=1,
        sale_mode="subscription@pro",
    )

    asyncio.run(tribute_service._create_shop_payment(service, request))

    service.create_shop_order.assert_awaited_once()
    assert service.create_shop_order.await_args.kwargs["amount"] == 149.0
    assert service.create_shop_order.await_args.kwargs["regular_amount"] == 199.0


def test_cancel_conflicting_shop_recurrence_uses_official_endpoint(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    http_session = object()
    get_session = AsyncMock(return_value=http_session)
    post = AsyncMock(
        return_value=(
            True,
            {"success": True, "message": "recurring order cancelled"},
        )
    )
    monkeypatch.setattr(service, "_get_session", get_session)
    monkeypatch.setattr(tribute_service, "post_json_request", post)

    cancelled = asyncio.run(service._cancel_shop_order(SHOP_ORDER_UUID))

    assert cancelled is True
    post.assert_awaited_once()
    call = post.await_args
    assert call is not None
    assert call.args == (
        http_session,
        f"https://tribute.tg/api/v1/shop/orders/{SHOP_ORDER_UUID}/cancel",
    )
    assert call.kwargs["body"] == {}
    assert call.kwargs["headers"] == {"Api-Key": API_KEY}
    assert call.kwargs["is_success"](200, {"success": True}) is True
    assert call.kwargs["is_success"](400, {"success": False}) is True
    assert call.kwargs["is_success"](500, {"success": False}) is False


def test_cancel_conflicting_shop_recurrence_accepts_already_cancelled(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        tribute_service,
        "post_json_request",
        AsyncMock(
            return_value=(
                True,
                {"error": "error_already_cancelled"},
            )
        ),
    )

    assert asyncio.run(service._cancel_shop_order(SHOP_ORDER_UUID)) is True


def _shop_transactions(
    *transactions: dict[str, object],
) -> TributeShopTransactionsResponse:
    return TributeShopTransactionsResponse.model_validate(
        {
            "transactions": list(transactions),
            "nextFrom": "",
        }
    )


def _shop_sell_transaction(
    *,
    transaction_id: int = 12345,
    amount: float = 99.0,
    currency: str = "rub",
    is_refunded: bool = False,
    is_refundable: bool = True,
) -> dict[str, object]:
    return {
        "id": transaction_id,
        "type": "shop_order_sell",
        "amount": amount,
        "currency": currency,
        "isRefunded": is_refunded,
        "isRefundable": is_refundable,
    }


def test_refund_shop_order_exact_sell_posts_matching_transaction(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(
        service,
        "_get_shop_order_transactions",
        AsyncMock(return_value=_shop_transactions(_shop_sell_transaction())),
    )
    http_session = object()
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=http_session))
    post = AsyncMock(
        return_value=(
            True,
            {
                "success": True,
                "message": "refund initiated",
                "status": "initiated",
            },
        )
    )
    monkeypatch.setattr(tribute_service, "post_json_request", post)

    result = asyncio.run(
        service._refund_shop_order_exact_sell(
            SHOP_ORDER_UUID,
            expected_amount=Decimal("99.0"),
            expected_currency="RUB",
        )
    )

    assert result == "initiated"
    call = post.await_args
    assert call is not None
    assert call.args == (
        http_session,
        f"https://tribute.tg/api/v1/shop/orders/{SHOP_ORDER_UUID}/transactions/12345/refund",
    )
    assert call.kwargs["body"] == {}
    assert call.kwargs["headers"] == {"Api-Key": API_KEY}


@pytest.mark.parametrize(
    "transactions",
    [
        _shop_transactions(),
        _shop_transactions(_shop_sell_transaction(amount=98.0)),
        _shop_transactions(_shop_sell_transaction(currency="usd")),
        _shop_transactions(
            _shop_sell_transaction(transaction_id=1),
            _shop_sell_transaction(transaction_id=2),
        ),
    ],
)
def test_refund_shop_order_exact_sell_rejects_missing_or_ambiguous_transaction(
    monkeypatch,
    transactions: TributeShopTransactionsResponse,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(
        service,
        "_get_shop_order_transactions",
        AsyncMock(return_value=transactions),
    )
    get_session = AsyncMock()
    monkeypatch.setattr(service, "_get_session", get_session)

    result = asyncio.run(
        service._refund_shop_order_exact_sell(
            SHOP_ORDER_UUID,
            expected_amount=Decimal("99"),
            expected_currency="rub",
        )
    )

    assert result is None
    get_session.assert_not_awaited()


def test_refund_shop_order_exact_sell_accepts_already_refunded(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(
        service,
        "_get_shop_order_transactions",
        AsyncMock(
            return_value=_shop_transactions(
                _shop_sell_transaction(is_refunded=True, is_refundable=False)
            )
        ),
    )
    get_session = AsyncMock()
    monkeypatch.setattr(service, "_get_session", get_session)

    result = asyncio.run(
        service._refund_shop_order_exact_sell(
            SHOP_ORDER_UUID,
            expected_amount=Decimal("99"),
            expected_currency="rub",
        )
    )

    assert result == "already_refunded"
    get_session.assert_not_awaited()


def test_refund_shop_order_exact_sell_api_failure_is_retryable(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(
        service,
        "_get_shop_order_transactions",
        AsyncMock(return_value=_shop_transactions(_shop_sell_transaction())),
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        tribute_service,
        "post_json_request",
        AsyncMock(return_value=(False, {"message": "refund_failed"})),
    )

    result = asyncio.run(
        service._refund_shop_order_exact_sell(
            SHOP_ORDER_UUID,
            expected_amount=Decimal("99"),
            expected_currency="rub",
        )
    )

    assert result is None


def test_refund_shop_order_exact_sell_accepts_post_race_already_refunded(
    monkeypatch,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(
        service,
        "_get_shop_order_transactions",
        AsyncMock(return_value=_shop_transactions(_shop_sell_transaction())),
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        tribute_service,
        "post_json_request",
        AsyncMock(return_value=(True, {"error": "error_already_refunded"})),
    )

    result = asyncio.run(
        service._refund_shop_order_exact_sell(
            SHOP_ORDER_UUID,
            expected_amount=Decimal("99"),
            expected_currency="rub",
        )
    )

    assert result == "already_refunded"


@pytest.mark.parametrize("amount", [0.99, 3000.01])
def test_create_shop_order_rejects_out_of_bounds_amount_before_network(
    monkeypatch,
    amount: float,
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    get_session = AsyncMock()
    monkeypatch.setattr(service, "_get_session", get_session)

    success, result = asyncio.run(
        service.create_shop_order(
            payment_db_id=85,
            user_id=42,
            amount=amount,
            currency="RUB",
            title="Remnawave purchase",
            description="Stored payment snapshot",
            months=10,
            sale_mode="topup@pro",
        )
    )

    assert success is False
    assert result["message"] == "invalid_shop_order"
    get_session.assert_not_awaited()


@pytest.mark.parametrize(
    ("config", "months", "sale_mode", "expected_message"),
    [
        (
            TributeConfig(ENABLED=True, API_KEY=API_KEY, SHOP_ENABLED=False),
            1,
            "subscription@pro",
            "shop_not_enabled",
        ),
        (
            TributeConfig(
                ENABLED=True,
                API_KEY=API_KEY,
                SHOP_ENABLED=True,
                SHOP_ID=SHOP_ID,
            ),
            2,
            "subscription@pro",
            "unsupported_payment_context",
        ),
        (
            TributeConfig(
                ENABLED=True,
                API_KEY=API_KEY,
                SHOP_ENABLED=True,
                SHOP_ID=SHOP_ID,
            ),
            1,
            "hwid_renewal@pro",
            "unsupported_payment_context",
        ),
    ],
)
def test_create_shop_order_fails_closed_before_network_for_unsupported_context(
    monkeypatch,
    config: TributeConfig,
    months: int,
    sale_mode: str,
    expected_message: str,
) -> None:
    service = _service(config=config)
    get_session = AsyncMock()
    post = AsyncMock()
    monkeypatch.setattr(service, "_get_session", get_session)
    monkeypatch.setattr(tribute_service, "post_json_request", post)

    success, result = asyncio.run(
        service.create_shop_order(
            payment_db_id=85,
            user_id=42,
            amount=149.0,
            currency="RUB",
            title="Remnawave purchase",
            description="Stored payment snapshot",
            months=months,
            sale_mode=sale_mode,
        )
    )

    assert success is False
    assert result["message"] == expected_message
    get_session.assert_not_awaited()
    post.assert_not_awaited()


@pytest.mark.parametrize(
    "provider_response",
    [
        _shop_order_response(payment_url="javascript:alert(1)"),
        _shop_order_response(payment_url="https://evil.example/pay"),
        _shop_order_response(webapp_payment_url="https://evil.example/pay"),
        {key: value for key, value in _shop_order_response().items() if key != "uuid"},
        {
            key: value
            for key, value in _shop_order_response(payment_url=None).items()
            if key != "webappPaymentUrl"
        },
        {**_shop_order_response(), "shopId": SHOP_ID + 1},
        {**_shop_order_response(), "amount": 14899},
        {**_shop_order_response(), "currency": "usd"},
        {**_shop_order_response(), "period": "monthly"},
        {**_shop_order_response(), "status": "paid"},
        {**_shop_order_response(), "firstPeriodAmount": 9900},
    ],
)
def test_create_shop_order_rejects_invalid_provider_response(
    monkeypatch,
    provider_response: dict[str, object],
) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    monkeypatch.setattr(service, "_get_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        tribute_service,
        "post_json_request",
        AsyncMock(
            return_value=(
                True,
                provider_response,
            )
        ),
    )

    success, result = asyncio.run(
        service.create_shop_order(
            payment_db_id=85,
            user_id=42,
            amount=149.0,
            currency="RUB",
            title="Remnawave purchase",
            description="Stored payment snapshot",
            months=50,
            sale_mode="traffic_package@traffic",
        )
    )

    assert success is False
    assert result["message"] == "invalid_shop_response"


def test_shop_order_response_accepts_missing_optional_webapp_payment_url() -> None:
    provider_response = _shop_order_response()
    provider_response.pop("webappPaymentUrl")

    parsed = TributeShopOrderResponse.model_validate(provider_response)

    assert parsed.payment_url == "https://tribute.tg/shop/pay/order"
    assert parsed.webapp_payment_url is None


def test_shop_checkout_resolver_uses_creator_fallback_for_unsupported_period() -> None:
    settings = _settings(_tariff(period_ids={"2": 202}))
    settings.TRIBUTE_SHOP_ENABLED = True
    settings.TRIBUTE_SHOP_ID = SHOP_ID

    assert tribute_service.tribute_supports_checkout(
        settings,
        50,
        "traffic_package@traffic",
    )
    assert tribute_service.tribute_supports_checkout(
        settings,
        2,
        "subscription@pro",
    )
    assert not tribute_service.tribute_supports_checkout(
        settings,
        2,
        "subscription@missing",
    )


def test_shop_limit_metadata_is_exposed_only_when_dynamic_shop_is_enabled() -> None:
    enabled = TributeConfig(
        ENABLED=True,
        API_KEY=API_KEY,
        SHOP_ENABLED=True,
        SHOP_ID=SHOP_ID,
    )
    disabled = TributeConfig(
        ENABLED=True,
        API_KEY=API_KEY,
        SHOP_ENABLED=False,
    )

    assert tribute_service.tribute_shop_amount_metadata(enabled, "RUB") == {
        "shop_min_amount": 1.0,
        "shop_max_amount": 3000.0,
        "shop_limit_currency": "RUB",
    }
    assert tribute_service.tribute_shop_amount_metadata(disabled, "RUB") is None
    # The context-free filter must not hide Creator fixed links with
    # provider-managed pricing outside the dynamic Shop range.
    assert tribute_service.tribute_shop_amount_supported(enabled, "RUB", 0.99)
    assert tribute_service.tribute_shop_amount_supported(enabled, "RUB", 3000.01)


def test_tribute_checkout_promo_policy_matches_shop_capabilities() -> None:
    settings = SimpleNamespace(TRIBUTE_SHOP_ENABLED=True, TRIBUTE_SHOP_ID=SHOP_ID)
    discount = SimpleNamespace(
        discount_amount=20.0,
        effects=SimpleNamespace(
            bonus_days=0,
            duration_multiplier=1.0,
            traffic_multiplier=1.0,
        ),
    )
    bonus_days = SimpleNamespace(
        discount_amount=20.0,
        effects=SimpleNamespace(
            bonus_days=7,
            duration_multiplier=1.0,
            traffic_multiplier=1.0,
        ),
    )

    assert tribute_service.tribute_checkout_promo_supported(
        settings,
        1,
        "subscription@pro",
        discount,
    )
    assert not tribute_service.tribute_checkout_promo_supported(
        settings,
        1,
        "subscription@pro",
        bonus_days,
    )
    assert tribute_service.tribute_checkout_promo_supported(
        settings,
        50,
        "traffic_package@traffic",
        bonus_days,
    )
    assert not tribute_service.tribute_checkout_promo_supported(
        SimpleNamespace(TRIBUTE_SHOP_ENABLED=False),
        1,
        "subscription@pro",
        discount,
    )
    assert not tribute_service.tribute_checkout_promo_supported(
        settings,
        2,
        "subscription@pro",
        discount,
    )


def test_billing_quote_rejects_unsupported_tribute_promo_before_checkout() -> None:
    promo = SimpleNamespace(
        discount_amount=20.0,
        effects=SimpleNamespace(
            bonus_days=7,
            duration_multiplier=1.0,
            traffic_multiplier=1.0,
        ),
    )

    error = billing_payments._payment_promo_error(
        settings=SimpleNamespace(TRIBUTE_SHOP_ENABLED=True, TRIBUTE_SHOP_ID=SHOP_ID),
        method="tribute",
        months=1,
        sale_mode="subscription@pro",
        promo_result=promo,
    )

    assert error is not None
    assert error.code == "promo_not_supported_by_payment_method"


def test_shop_without_a_shop_id_falls_back_to_creator_subscriptions() -> None:
    """A flag with no shop behind it must not advertise Shop-only checkouts.

    The panel writes provider overrides with a plain assignment, which does not
    re-run the validator pairing the flag with the ID, so this state is
    reachable from the admin UI.
    """

    settings = _settings(_tariff(period_ids={"1": 201}))
    settings.TRIBUTE_SHOP_ENABLED = True
    settings.TRIBUTE_SHOP_ID = None

    # Periods that a Creator subscription covers stay purchasable...
    assert tribute_service.tribute_supports_checkout(settings, 1, "subscription@pro")
    assert tribute_service.tribute_price_managed_externally(settings, 1, "subscription@pro")
    # ...and everything only Shop Orders can price does not.
    for sale_mode in ("hwid_devices@pro", "tariff_upgrade@pro"):
        assert not tribute_service.tribute_supports_checkout(settings, 1, sale_mode)
    assert tribute_service.tribute_shop_amount_metadata(settings, "RUB") is None

    settings.TRIBUTE_SHOP_ID = SHOP_ID
    assert tribute_service.tribute_supports_checkout(settings, 1, "hwid_devices@pro")


def test_service_shop_mode_requires_a_configured_shop_id() -> None:
    configured = _service(
        config=TributeConfig(ENABLED=True, API_KEY=API_KEY, SHOP_ENABLED=True, SHOP_ID=SHOP_ID)
    )
    assert configured.shop_enabled is True

    service = _service(config=TributeConfig(ENABLED=True, API_KEY=API_KEY))
    service.config.SHOP_ENABLED = True
    service.config.SHOP_ID = None

    assert service.shop_enabled is False


def test_service_declares_and_cancels_provider_managed_shop_recurrence(monkeypatch) -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    session = SimpleNamespace()
    active_shop_order = AsyncMock(return_value=SHOP_ORDER_UUID)
    active_creator_subscription = AsyncMock(return_value=None)
    cancel_order = AsyncMock(return_value=True)
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_shop_order_uuid",
        active_shop_order,
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_creator_subscription_id",
        active_creator_subscription,
    )
    monkeypatch.setattr(service, "_cancel_shop_order", cancel_order)

    cancelled = asyncio.run(service.cancel_provider_recurrence(session, user_id=42))

    assert tribute_service.SPEC.manages_recurring is True
    assert tribute_service.SPEC.supports_checkout_addon_first_period is True
    assert service.manages_recurrence is True
    assert cancelled is True
    cancel_order.assert_awaited_once_with(SHOP_ORDER_UUID)


def test_service_refuses_local_disable_for_uncancellable_creator_subscription(
    monkeypatch,
) -> None:
    service = _service(config=TributeConfig(ENABLED=True, API_KEY=API_KEY))
    session = SimpleNamespace()
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_shop_order_uuid",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        tribute_service.tribute_dal,
        "get_other_active_creator_subscription_id",
        AsyncMock(return_value=101),
    )

    cancelled = asyncio.run(service.cancel_provider_recurrence(session, user_id=42))

    assert service.manages_recurrence is True
    assert cancelled is False


def test_each_period_can_be_sold_by_its_own_tribute_subscription() -> None:
    tariff = _tariff(
        link=None,
        subscription_id=None,
        period_ids={"1": 201, "12": 4001},
        period_links={
            "1": "https://t.me/tribute/app?startapp=ep_monthly",
            "12": "https://t.me/tribute/app?startapp=ep_yearly",
        },
        period_subscription_ids={"1": 101, "12": 909},
    )
    settings = _settings(tariff)

    monthly = tribute_service._binding_for_checkout(
        settings, sale_mode="subscription@pro", months=1
    )
    yearly = tribute_service._binding_for_checkout(
        settings, sale_mode="subscription@pro", months=12
    )

    assert monthly is not None and yearly is not None
    assert monthly.link.endswith("ep_monthly")
    assert monthly.subscription_id == 101
    assert yearly.link.endswith("ep_yearly")
    assert yearly.subscription_id == 909
    # A webhook is attributed by the subscription that actually sold it.
    binding = tribute_service._binding_for_event(
        settings,
        _payload(subscription_id=909, period_id=4001),
    )
    assert binding is not None
    assert binding.months == 12
    assert binding.tariff_key == "pro"


def test_tribute_price_authority_switches_between_shop_and_static_fallback() -> None:
    settings = _settings(_tariff(period_ids={"2": 202}))
    settings.TRIBUTE_SHOP_ENABLED = True
    settings.TRIBUTE_SHOP_ID = SHOP_ID

    assert not tribute_service.tribute_price_managed_externally(
        settings,
        50,
        "traffic_package@traffic",
    )
    assert tribute_service.tribute_price_managed_externally(
        settings,
        2,
        "subscription@pro",
    )

    settings.TRIBUTE_SHOP_ENABLED = False
    assert tribute_service.tribute_price_managed_externally(
        settings,
        2,
        "subscription@pro",
    )


def test_try_reuse_shop_order_requires_both_uuid_and_payment_url() -> None:
    service = _service(
        config=TributeConfig(
            ENABLED=True,
            API_KEY=API_KEY,
            SHOP_ENABLED=True,
            SHOP_ID=SHOP_ID,
        )
    )
    payment = _shop_payment()

    assert asyncio.run(service.try_reuse_shop_order(payment)) == payment.provider_payment_url
    payment.provider_payment_id = None
    assert asyncio.run(service.try_reuse_shop_order(payment)) is None
    payment.provider_payment_id = SHOP_ORDER_UUID
    payment.provider_payment_url = None
    assert asyncio.run(service.try_reuse_shop_order(payment)) is None


@pytest.mark.parametrize(
    "payment_options",
    [
        {
            "sale_mode": "traffic_package@traffic",
            "tariff_key": "traffic",
            "months": 50,
            "purchased_gb": 50,
        },
        {
            "sale_mode": "topup@pro",
            "tariff_key": "pro",
            "months": 10,
            "purchased_gb": 10,
        },
        {
            "sale_mode": "premium_topup@pro",
            "tariff_key": "pro",
            "months": 5,
            "purchased_gb": 5,
        },
        {
            "sale_mode": "hwid_devices@pro",
            "tariff_key": "pro",
            "months": 1,
            "purchased_gb": None,
            "purchased_hwid_devices": 1,
        },
        {
            "sale_mode": "tariff_upgrade@pro",
            "tariff_key": "pro",
            "months": 1,
            "purchased_gb": None,
        },
    ],
)
def test_shop_order_one_time_success_finalizes_stored_purchase_snapshot(
    monkeypatch,
    payment_options: _ShopPaymentOptions,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(**payment_options)
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(amount=14900),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    mocks.lookup.assert_awaited()
    lookup_args = mocks.lookup.await_args
    assert SHOP_ORDER_UUID in lookup_args.args or SHOP_ORDER_UUID in lookup_args.kwargs.values()
    success_request = mocks.finalize.await_args.args[0]
    assert success_request.payment is payment
    assert success_request.sale_mode == payment.sale_mode
    assert success_request.amount == payment.amount
    assert success_request.currency == payment.currency
    assert success_request.skip_referral_bonus is True
    assert "authoritative_end_at" not in success_request.activation_extra_kwargs
    assert event.status == "processed"
    assert event.payment_id == payment.payment_id


def test_shop_second_pending_upgrade_with_changed_source_is_refunded_without_activation(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(
        settings=_settings(
            _tariff(key="basic", subscription_id=100),
            _tariff(key="pro", subscription_id=101),
        ),
        session=session,
    )
    payment = _quoted_tariff_upgrade_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    # A first pending upgrade won the user lock and already changed the source
    # subscription before this independently paid order arrived.
    mocks.active_subscription.return_value = _active_tariff_subscription("pro")

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(amount=7550),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "reason": "source_tariff_changed",
        "refund_status": "initiated",
    }
    mocks.user.assert_awaited_once_with(session, 42)
    mocks.active_subscription.assert_awaited_once_with(session, 42)
    mocks.refund_order.assert_awaited_once_with(
        SHOP_ORDER_UUID,
        expected_amount=Decimal("75.5"),
        expected_currency="RUB",
    )
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "failed")
    assert event.status == "quarantined"
    assert event.status_reason == "stale_paid_entitlement:source_tariff_changed"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_stale_upgrade_refund_failure_is_retryable(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(
        settings=_settings(
            _tariff(key="basic", subscription_id=100),
            _tariff(key="pro", subscription_id=101),
        ),
        session=session,
    )
    payment = _quoted_tariff_upgrade_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = _active_tariff_subscription("pro")
    mocks.refund_order.return_value = None

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload(amount=7550)),
        )
    )

    assert response.status == 503
    assert _response_json(response)["error"] == "stale_entitlement_refund_failed"
    session.rollback.assert_awaited_once()
    mocks.update_payment_status.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "processing"


def test_shop_stale_upgrade_already_refunded_is_terminal(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(
        settings=_settings(
            _tariff(key="basic", subscription_id=100),
            _tariff(key="pro", subscription_id=101),
        ),
        session=session,
    )
    payment = _quoted_tariff_upgrade_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = _active_tariff_subscription("pro")
    mocks.refund_order.return_value = "already_refunded"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload(amount=7550)),
        )
    )

    assert response.status == 200
    assert _response_json(response)["refund_status"] == "already_refunded"
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "refunded")
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "quarantined"


def test_shop_stale_addon_context_uses_the_same_exact_refund_path(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    quoted_subscription = SimpleNamespace(subscription_id=501, tariff_key="pro")
    payment = _shop_payment(
        amount=50.0,
        sale_mode="topup@pro",
        tariff_key="pro",
        months=10,
        purchased_gb=10,
        entitlement_context_snapshot=build_entitlement_context_snapshot(
            sale_mode="topup@pro",
            active_subscription=quoted_subscription,
        ),
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=502,
        tariff_key="pro",
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload(amount=5000)),
        )
    )

    assert response.status == 200
    assert _response_json(response)["reason"] == "active_subscription_changed"
    mocks.refund_order.assert_awaited_once_with(
        SHOP_ORDER_UUID,
        expected_amount=Decimal("50.0"),
        expected_currency="RUB",
    )
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "failed")
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "quarantined"


def test_shop_invalid_addon_snapshot_is_quarantined_without_refund_or_activation(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=50.0,
        sale_mode="topup@pro",
        tariff_key="pro",
        months=10,
        purchased_gb=10,
        entitlement_context_snapshot="{}",
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload(amount=5000)),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "reason": "snapshot_schema_mismatch",
        "manual_review": True,
    }
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "failed")
    mocks.refund_order.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status_reason == "invalid_paid_entitlement:snapshot_schema_mismatch"


def test_shop_valid_upgrade_activation_failure_is_not_auto_refunded(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(
        settings=_settings(
            _tariff(key="basic", subscription_id=100),
            _tariff(key="pro", subscription_id=101),
        ),
        session=session,
    )
    payment = _quoted_tariff_upgrade_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = _active_tariff_subscription("basic")
    mocks.finalize.return_value = None

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload(amount=7550)),
        )
    )

    assert response.status == 500
    assert _response_json(response)["error"] == "activation_failed"
    mocks.refund_order.assert_not_awaited()
    mocks.claim.assert_awaited_once()
    mocks.finalize.assert_awaited_once()
    assert event.status == "processing"


def test_shop_completed_refund_settles_stale_upgrade_without_fulfilment(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _quoted_tariff_upgrade_payment()
    event = _shop_event(event_name="shop_order_refunded")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.quarantine_reason.return_value = "stale_paid_entitlement:source_tariff_changed"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(amount=7550, status="completed"),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "refunded",
        "manual_review": True,
    }
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "refunded")
    assert event.status == "processed"
    assert event.status_reason == "quarantined_order_refund_completed"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_order_accepts_the_customer_id_emitted_during_order_creation(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    webhook_payload = _shop_payload()
    webhook_payload["customerId"] = f"telegram:{payment.user_id}"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", webhook_payload),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    mocks.finalize.assert_awaited_once()


def test_shop_order_accepts_official_nonrecurring_example_period_metadata(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    is_recurrent=False,
                    period="monthly",
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    mocks.finalize.assert_awaited_once()


def test_shop_order_quarantines_different_customer_id(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    webhook_payload = _shop_payload()
    webhook_payload["customerId"] = "telegram:777"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", webhook_payload),
        )
    )

    assert response.status == 400
    assert _response_json(response)["reason"] == "customer_mismatch"
    assert event.status == "quarantined"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_order_quarantines_different_shop_id(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment()
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    webhook_payload = _shop_payload()
    webhook_payload["shopId"] = SHOP_ID + 1

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", webhook_payload),
        )
    )

    assert response.status == 400
    assert _response_json(response)["reason"] == "shop_id_mismatch"
    assert event.status == "quarantined"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("payload_overrides", "payment_overrides"),
    [
        ({"amount": 14899}, {}),
        ({"currency": "usd"}, {}),
        (
            {"is_recurrent": False, "period": "onetime"},
            {
                "sale_mode": "subscription@pro",
                "tariff_key": "pro",
                "months": 1,
                "purchased_gb": None,
            },
        ),
    ],
)
def test_shop_order_rejects_webhook_snapshot_mismatch(
    monkeypatch,
    payload_overrides: _ShopPayloadOptions,
    payment_overrides: _ShopPaymentOptions,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(**payment_overrides)
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    payload_options: _ShopPayloadOptions = {
        "amount": 14900,
        "currency": "rub",
        "is_recurrent": False,
        "period": "onetime",
    }
    payload_options.update(payload_overrides)

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(**payload_options),
            ),
        )
    )

    assert response.status == 400
    assert event.status == "quarantined"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_order_unknown_uuid_is_retryable(monkeypatch) -> None:
    service = _service()
    payment = _shop_payment()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
    )
    mocks.lookup.return_value = None

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    order_uuid="11111111-1111-4111-8111-111111111111",
                ),
            ),
        )
    )

    assert response.status == 404
    assert _response_json(response)["error"] == "payment_not_found"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_webhook_retry_fingerprint_excludes_sent_at(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(status="succeeded")
    event = _shop_event(status="processed")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    first = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(),
                sent_at=CREATED_AT + timedelta(seconds=1),
            ),
        )
    )
    retry = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(),
                sent_at=CREATED_AT + timedelta(hours=8),
            ),
        )
    )

    assert first.status == retry.status == 200
    assert len(mocks.ensure_event.await_args_list) == 2
    first_values = mocks.ensure_event.await_args_list[0].args[1]
    retry_values = mocks.ensure_event.await_args_list[1].args[1]
    assert first_values["fingerprint"] == retry_values["fingerprint"]
    assert first_values["event_sent_at"] != retry_values["event_sent_at"]
    mocks.finalize.assert_not_awaited()


def test_shop_recurring_initial_payment_uses_local_period_snapshot(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="pending_tribute",
        amount=79.0,
        checkout_base_amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )
    webhook_payload = _shop_payload(
        amount=9900,
        period="monthly",
        is_recurrent=True,
        first_period_amount=7900,
    )
    webhook_payload["memberStatus"] = "active"
    webhook_payload["memberExpiresAt"] = EXPIRES_AT.isoformat()

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                webhook_payload,
            ),
        )
    )

    assert response.status == 200
    success_request = mocks.finalize.await_args.args[0]
    assert success_request.sale_mode == "subscription@pro"
    assert success_request.amount == 79.0
    assert success_request.months == 1
    assert success_request.traffic_amount is None
    assert success_request.activation_extra_kwargs == {"authoritative_end_at": EXPIRES_AT}
    assert success_request.skip_referral_bonus is False
    mocks.set_auto_renew.assert_awaited_once_with(session, 501, True)


@pytest.mark.parametrize(
    ("first_period_amount", "expected_reason"),
    [
        (None, "first_period_amount_missing"),
        (7800, "first_period_amount_mismatch"),
    ],
)
def test_shop_discounted_recurring_initial_requires_exact_first_period_amount(
    monkeypatch,
    first_period_amount: int | None,
    expected_reason: str,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=79.0,
        checkout_base_amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=True,
                    first_period_amount=first_period_amount,
                ),
            ),
        )
    )

    assert response.status == 400
    assert _response_json(response)["reason"] == expected_reason
    assert event.status == "quarantined"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    "trial_metadata",
    [
        {"isTrial": True},
        {"trialPeriod": "seven_days"},
        {"trialEndsAt": EXPIRES_AT.isoformat()},
    ],
)
def test_shop_initial_order_quarantines_unrequested_trial_metadata(
    monkeypatch,
    trial_metadata: dict[str, object],
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    webhook_payload = _shop_payload(
        amount=9900,
        period="monthly",
        is_recurrent=True,
    )
    webhook_payload.update(trial_metadata)

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", webhook_payload),
        )
    )

    assert response.status == 400
    assert _response_json(response)["reason"] == "unsupported_trial"
    assert event.status == "quarantined"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_recurring_initial_rejects_false_recurrence_flag(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=False,
                ),
            ),
        )
    )

    assert response.status == 400
    assert _response_json(response) == {
        "ok": False,
        "error": "snapshot_mismatch",
        "reason": "recurrence_mismatch",
    }
    assert event.status == "quarantined"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("tombstone_reason", "expected_payment_status"),
    [
        ("completed_refund", "refunded"),
        ("last_charge_refunded", "refunded"),
        ("payment_failed", "failed"),
    ],
)
def test_shop_delayed_initial_success_after_refund_is_quarantined(
    monkeypatch,
    tombstone_reason: str,
    expected_payment_status: str,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.success_tombstone.return_value = tombstone_reason

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=True,
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "reason": tombstone_reason,
    }
    mocks.success_tombstone.assert_awaited_once_with(
        session,
        order_uuid=SHOP_ORDER_UUID,
        success_created_at=CREATED_AT,
        initial_success=True,
    )
    mocks.update_payment_status.assert_awaited_once_with(
        session,
        85,
        expected_payment_status,
    )
    assert event.status == "quarantined"
    assert event.status_reason == f"superseded_by_{tombstone_reason}"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_refund_of_older_charge_does_not_tombstone_delayed_newer_success(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    cycle_payment = _shop_payment(
        payment_id=86,
        status="pending_tribute",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
        provider_payment_id="shop_charge:" + ("a" * 64),
    )
    refund_event = _shop_event(event_name="shop_order_refunded")
    success_event = _shop_event(event_name="shop_order_charge_success")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=refund_event,
        cycle_payment=cycle_payment,
    )

    def ensure_event(_session: object, values: dict[str, object]):
        resolved = refund_event if values["event_name"] == "shop_order_refunded" else success_event
        return resolved, True

    def success_tombstone(
        _session: object,
        *,
        order_uuid: str,
        success_created_at: datetime,
        initial_success: bool,
    ) -> str | None:
        assert order_uuid == SHOP_ORDER_UUID
        assert success_created_at == CREATED_AT + timedelta(days=1)
        if initial_success and refund_event.status == "processed":
            return "completed_refund"
        return None

    mocks.ensure_event.side_effect = ensure_event
    mocks.success_tombstone.side_effect = success_tombstone
    mocks.claim.return_value = cycle_payment

    refund_response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(amount=9900, status="completed"),
                created_at=CREATED_AT + timedelta(days=2),
            ),
        )
    )

    assert refund_response.status == 200
    assert _response_json(refund_response) == {
        "ok": True,
        "status": "refunded",
        "manual_review": True,
    }
    assert refund_event.status == "processed"
    assert refund_event.status_reason == "manual_entitlement_review"
    mocks.update_payment_status.assert_not_awaited()

    success_response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(amount=9900),
                created_at=CREATED_AT + timedelta(days=1),
            ),
        )
    )

    assert success_response.status == 200
    assert _response_json(success_response) == {
        "ok": True,
        "status": "processed",
        "payment_id": 86,
    }
    mocks.success_tombstone.assert_awaited_once_with(
        session,
        order_uuid=SHOP_ORDER_UUID,
        success_created_at=CREATED_AT + timedelta(days=1),
        initial_success=False,
    )
    mocks.ensure_cycle.assert_awaited_once()
    mocks.finalize.assert_awaited_once()
    assert success_event.status == "processed"
    assert success_event.payment_id == 86


def test_shop_last_charge_refund_still_tombstones_delayed_recurring_success(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_charge_success")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.success_tombstone.return_value = "last_charge_refunded"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(amount=9900),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "reason": "last_charge_refunded",
    }
    mocks.success_tombstone.assert_awaited_once_with(
        session,
        order_uuid=SHOP_ORDER_UUID,
        success_created_at=CREATED_AT,
        initial_success=False,
    )
    mocks.ensure_cycle.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "quarantined"
    assert event.status_reason == "superseded_by_last_charge_refunded"


def test_shop_conflicting_paid_recurrence_is_cancelled_and_quarantined(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="pending_tribute",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    other_order = "770e8400-e29b-41d4-a716-446655440002"
    mocks.active_shop_order.return_value = other_order

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=True,
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "manual_review": True,
        "recurrence_cancelled": True,
        "refund_status": "initiated",
    }
    mocks.user.assert_awaited_once_with(session, 42)
    mocks.active_shop_order.assert_awaited_once_with(
        session,
        user_id=42,
        exclude_order_uuid=SHOP_ORDER_UUID,
    )
    mocks.cancel_order.assert_awaited_once_with(SHOP_ORDER_UUID)
    mocks.refund_order.assert_awaited_once_with(
        SHOP_ORDER_UUID,
        expected_amount=Decimal("99.0"),
        expected_currency="RUB",
    )
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "failed")
    assert event.status == "quarantined"
    assert event.status_reason == "duplicate_active_recurrence_manual_review"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_conflicting_recurrence_cancel_failure_is_retryable(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_creator_subscription.return_value = 777
    mocks.cancel_order.return_value = False

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=True,
                ),
            ),
        )
    )

    assert response.status == 503
    assert _response_json(response)["error"] == "conflicting_recurrence_cancel_failed"
    session.rollback.assert_awaited_once()
    mocks.refund_order.assert_not_awaited()
    mocks.update_payment_status.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_conflicting_recurrence_refund_failure_is_retryable(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_creator_subscription.return_value = 777
    mocks.refund_order.return_value = None

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=True,
                ),
            ),
        )
    )

    assert response.status == 503
    assert _response_json(response)["error"] == "conflicting_recurrence_refund_failed"
    mocks.cancel_order.assert_awaited_once_with(SHOP_ORDER_UUID)
    mocks.refund_order.assert_awaited_once()
    session.rollback.assert_awaited_once()
    mocks.update_payment_status.assert_not_awaited()
    assert event.status == "processing"
    mocks.finalize.assert_not_awaited()


def test_shop_conflicting_recurrence_already_refunded_is_idempotent(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_creator_subscription.return_value = 777
    mocks.refund_order.return_value = "already_refunded"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order",
                _shop_payload(
                    amount=9900,
                    period="monthly",
                    is_recurrent=True,
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["refund_status"] == "already_refunded"
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "refunded")
    assert event.status == "quarantined"
    mocks.finalize.assert_not_awaited()


def test_shop_charge_after_duplicate_quarantine_cannot_activate(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="failed",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_charge_success")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.quarantine_reason.return_value = "duplicate_active_recurrence_manual_review"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(amount=9900),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "quarantined",
        "manual_review": True,
    }
    mocks.ensure_cycle.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_completed_refund_marks_duplicate_recurrence_payment_refunded(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="failed",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_refunded")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.quarantine_reason.return_value = "duplicate_active_recurrence_manual_review"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(
                    amount=9900,
                    status="completed",
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "refunded",
        "manual_review": True,
    }
    mocks.update_payment_status.assert_awaited_once_with(session, 85, "refunded")
    assert event.status == "processed"
    assert event.status_reason == "duplicate_recurrence_refund_completed"
    mocks.finalize.assert_not_awaited()


def test_shop_recurring_charge_creates_one_cycle_payment_and_finalizes_it(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    initial_payment = _shop_payment(
        status="succeeded",
        amount=79.0,
        checkout_base_amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
        entitlement_context_snapshot='{"version":1}',
    )
    initial_payment.checkout_bundle_snapshot = '{"version":1,"addons":[]}'
    initial_payment.checkout_bundle_hash = "b" * 64
    cycle_payment = _shop_payment(
        payment_id=86,
        status="pending_tribute",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
        provider_payment_id="placeholder",
    )
    event = _shop_event(event_name="shop_order_charge_success")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=initial_payment,
        event=event,
        cycle_payment=cycle_payment,
    )
    mocks.claim.return_value = cycle_payment
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )
    webhook_payload = _shop_charge_payload(
        amount=9900,
        first_period_amount=7900,
    )
    webhook_payload["memberStatus"] = "active"
    webhook_payload["memberExpiresAt"] = EXPIRES_AT.isoformat()

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                webhook_payload,
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "processed",
        "payment_id": 86,
    }
    event_values = mocks.ensure_event.await_args.args[1]
    fingerprint = event_values["fingerprint"]
    mocks.ensure_cycle.assert_awaited_once()
    cycle_args = mocks.ensure_cycle.await_args
    assert cycle_args.args == (session,)
    assert cycle_args.kwargs["provider_payment_id"] == (
        f"shop_charge:{SHOP_ORDER_UUID}:{fingerprint}"
    )
    assert cycle_args.kwargs["user_id"] == initial_payment.user_id
    assert cycle_args.kwargs["amount"] == initial_payment.checkout_base_amount
    assert cycle_args.kwargs["currency"] == initial_payment.currency
    assert cycle_args.kwargs["months"] == 1
    assert cycle_args.kwargs["sale_mode"] == "subscription@pro"
    assert cycle_args.kwargs["entitlement_context_snapshot"] == '{"version":1}'
    assert cycle_args.kwargs["checkout_bundle_snapshot"] == ('{"version":1,"addons":[]}')
    assert cycle_args.kwargs["checkout_bundle_hash"] == "b" * 64
    assert cycle_payment.is_auto_renew is True
    success_request = mocks.finalize.await_args.args[0]
    assert success_request.payment is cycle_payment
    assert success_request.user_id == initial_payment.user_id
    assert success_request.amount == 99.0
    assert success_request.months == 1
    assert success_request.traffic_amount is None
    assert success_request.activation_extra_kwargs == {"authoritative_end_at": EXPIRES_AT}
    assert success_request.skip_referral_bonus is False
    assert event.status == "processed"
    assert event.payment_id == cycle_payment.payment_id
    mocks.set_auto_renew.assert_awaited_once_with(session, 501, True)


def test_shop_delayed_recurring_charge_grants_access_without_reenabling_after_cancel(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    initial_payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    cycle_payment = _shop_payment(
        payment_id=86,
        status="pending_tribute",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
        provider_payment_id="placeholder",
    )
    event = _shop_event(event_name="shop_order_charge_success")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=initial_payment,
        event=event,
        cycle_payment=cycle_payment,
    )
    mocks.claim.return_value = cycle_payment
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )
    # The DAL has observed a cancellation with a later provider timestamp.
    mocks.recurring_state.side_effect = None
    mocks.recurring_state.return_value = "inactive"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(),
                created_at=CREATED_AT,
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "processed"
    mocks.finalize.assert_awaited_once()
    mocks.recurring_state.assert_awaited_once_with(session, SHOP_ORDER_UUID)
    mocks.set_auto_renew.assert_awaited_once_with(session, 501, False)
    assert event.status == "processed"
    assert event.payment_id == cycle_payment.payment_id


@pytest.mark.parametrize(
    ("payment", "payload"),
    [
        (
            _shop_payment(
                amount=99.0,
                sale_mode="subscription@pro",
                tariff_key="pro",
                months=1,
                purchased_gb=None,
            ),
            _shop_charge_payload(amount=9800),
        ),
        (
            _shop_payment(
                amount=99.0,
                sale_mode="subscription@pro",
                tariff_key="pro",
                months=1,
                purchased_gb=None,
            ),
            _shop_charge_payload(currency="usd"),
        ),
        (
            _shop_payment(
                amount=99.0,
                sale_mode="subscription@pro",
                tariff_key="pro",
                months=1,
                purchased_gb=None,
            ),
            _shop_charge_payload(period="quarterly"),
        ),
        (
            _shop_payment(),
            _shop_charge_payload(amount=14900),
        ),
    ],
)
def test_shop_recurring_charge_quarantines_snapshot_mismatch(
    monkeypatch,
    payment: SimpleNamespace,
    payload: dict[str, object],
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    event = _shop_event(event_name="shop_order_charge_success")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                payload,
            ),
        )
    )

    assert response.status == 400
    assert _response_json(response)["error"] == "snapshot_mismatch"
    assert event.status == "quarantined"
    assert event.payment_id == payment.payment_id
    mocks.ensure_cycle.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_recurring_charge_resume_after_cycle_payment_committed(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    initial_payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    cycle_payment = _shop_payment(
        payment_id=86,
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
        provider_payment_id="shop_charge:already-finalized",
    )
    event = _shop_event(
        event_name="shop_order_charge_success",
        payment_id=cycle_payment.payment_id,
    )
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=initial_payment,
        event=event,
        cycle_payment=cycle_payment,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["duplicate"] is True
    assert event.status == "processed"
    assert event.payment_id == cycle_payment.payment_id
    mocks.recurring_state.assert_awaited_once_with(session, SHOP_ORDER_UUID)
    mocks.set_auto_renew.assert_awaited_once_with(session, 501, True)
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("fresh_status", "expected_status", "expected_error"),
    [
        ("succeeded", 200, None),
        ("pending_tribute", 503, "activation_in_progress"),
    ],
)
def test_shop_initial_payment_concurrent_finalization_is_resumable(
    monkeypatch,
    fresh_status: str,
    expected_status: int,
    expected_error: str | None,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(status="pending_tribute")
    event = _shop_event()
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.claim.return_value = None
    mocks.get_payment.return_value = _shop_payment(status=fresh_status)

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload()),
        )
    )

    assert response.status == expected_status
    body = _response_json(response)
    if expected_error is None:
        assert body["status"] == "processed"
        assert event.status == "processed"
    else:
        assert body["error"] == expected_error
        assert event.status == "processing"
    mocks.finalize.assert_not_awaited()


def test_shop_cancel_disables_auto_renew_without_shortening_access(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_cancelled")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    access_end = EXPIRES_AT
    subscription = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
        end_date=access_end,
    )
    mocks.active_subscription.return_value = subscription
    webhook_payload = _shop_charge_payload()
    webhook_payload["cancelReason"] = "cancelled_by_seller"

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_cancelled",
                webhook_payload,
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "cancelled"
    assert subscription.end_date == access_end
    mocks.set_auto_renew.assert_awaited_once_with(session, 501, False)
    mocks.update_payment_status.assert_not_awaited()
    mocks.ensure_cycle.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "processed"
    assert event.status_reason == "cancelled_by_seller"


@pytest.mark.parametrize(
    ("charge_retries", "should_disable"),
    [(1, False), (3, True)],
)
def test_shop_charge_failure_waits_for_provider_retries_before_disabling_renewal(
    monkeypatch,
    charge_retries: int,
    should_disable: bool,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_charge_failed")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )
    webhook_payload = _shop_charge_payload()
    webhook_payload["chargeRetries"] = charge_retries

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_failed",
                webhook_payload,
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "charge_failed"
    assert event.status == "processed"
    assert event.status_reason == f"charge_retry_{charge_retries}"
    if should_disable:
        mocks.set_auto_renew.assert_awaited_once_with(session, 501, False)
    else:
        mocks.set_auto_renew.assert_not_awaited()
    mocks.update_payment_status.assert_not_awaited()
    mocks.ensure_cycle.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_delayed_final_charge_failure_keeps_renewal_after_newer_success(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_charge_failed")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )
    # The DAL has observed a successful charge with a later provider timestamp.
    mocks.recurring_state.side_effect = None
    mocks.recurring_state.return_value = "active"
    webhook_payload = _shop_charge_payload()
    webhook_payload["chargeRetries"] = 3

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_failed",
                webhook_payload,
                created_at=CREATED_AT,
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "charge_failed"
    mocks.recurring_state.assert_awaited_once_with(session, SHOP_ORDER_UUID)
    mocks.set_auto_renew.assert_awaited_once_with(session, 501, True)
    mocks.finalize.assert_not_awaited()
    assert event.status == "processed"
    assert event.status_reason == "charge_retry_3"


def test_shop_initial_payment_failure_marks_payment_failed_without_activation(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(status="pending_tribute")
    event = _shop_event(event_name="shop_order_payment_failed")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    webhook_payload = {
        "uuid": SHOP_ORDER_UUID,
        "shopId": SHOP_ID,
        "amount": 14900,
        "currency": "rub",
        "errorCode": "payment_declined",
        "errorMessage": "Card declined",
    }

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_payment_failed",
                webhook_payload,
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "failed"
    mocks.update_payment_status.assert_awaited_once_with(
        session,
        payment.payment_id,
        "failed",
    )
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "processed"
    assert event.status_reason == "payment_declined"


@pytest.mark.parametrize(
    ("sale_mode", "should_mark_refunded"),
    [
        ("traffic_package@traffic", True),
        ("subscription@pro", False),
    ],
)
def test_shop_refund_records_manual_review_without_entitlement_clawback(
    monkeypatch,
    sale_mode: str,
    should_mark_refunded: bool,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        sale_mode=sale_mode,
        tariff_key="pro" if sale_mode == "subscription@pro" else "traffic",
        months=1 if sale_mode == "subscription@pro" else 50,
        purchased_gb=None if sale_mode == "subscription@pro" else 50,
    )
    event = _shop_event(event_name="shop_order_refunded")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(status="completed"),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "refunded",
        "manual_review": True,
    }
    if should_mark_refunded:
        mocks.update_payment_status.assert_awaited_once_with(
            session,
            payment.payment_id,
            "refunded",
        )
    else:
        mocks.update_payment_status.assert_not_awaited()
    mocks.set_auto_renew.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "processed"
    assert event.status_reason == "manual_entitlement_review"
    assert event.payment_id == payment.payment_id


@pytest.mark.parametrize("refunded_amount", [7900, 9900])
def test_shop_discounted_recurrence_refund_accepts_initial_or_regular_charge(
    monkeypatch,
    refunded_amount: int,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=79.0,
        checkout_base_amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_refunded")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(
                    amount=refunded_amount,
                    first_period_amount=7900,
                    status="completed",
                ),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response)["status"] == "refunded"
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_refund_rejects_amount_outside_discounted_recurrence_snapshot(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=79.0,
        checkout_base_amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name="shop_order_refunded")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(
                    amount=8900,
                    first_period_amount=7900,
                    status="completed",
                ),
            ),
        )
    )

    assert response.status == 400
    assert _response_json(response)["reason"] == "amount_mismatch"
    mocks.update_payment_status.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_refund_initiated_is_recorded_without_accounting_mutation(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(status="succeeded")
    event = _shop_event(event_name="shop_order_refunded")
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_refunded",
                _shop_refund_payload(status="initiated"),
            ),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "refund_initiated",
        "manual_review": False,
    }
    mocks.update_payment_status.assert_not_awaited()
    mocks.set_auto_renew.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()
    assert event.status == "processed"
    assert event.status_reason == "refund_initiated"
    assert event.payment_id == payment.payment_id


def test_shop_processed_event_is_idempotent_before_any_side_effect(monkeypatch) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(status="succeeded")
    event = _shop_event(status="processed", payment_id=payment.payment_id)
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload("shop_order", _shop_payload()),
        )
    )

    assert response.status == 200
    assert _response_json(response) == {
        "ok": True,
        "status": "processed",
        "duplicate": True,
    }
    mocks.ensure_cycle.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.get_payment.assert_not_awaited()
    mocks.update_payment_status.assert_not_awaited()
    mocks.set_auto_renew.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("event_name", "webhook_payload"),
    [
        (
            "shop_order_charge_failed",
            {
                **_shop_charge_payload(amount=1),
                "chargeRetries": 3,
            },
        ),
        (
            "shop_order_cancelled",
            {
                **_shop_charge_payload(amount=1),
                "cancelReason": "cancelled_by_seller",
            },
        ),
        (
            "shop_order_payment_failed",
            {
                "uuid": SHOP_ORDER_UUID,
                "shopId": SHOP_ID,
                "amount": 1,
                "currency": "rub",
                "errorCode": "payment_declined",
                "errorMessage": "Card declined",
            },
        ),
        (
            "shop_order_refunded",
            _shop_refund_payload(amount=1),
        ),
    ],
)
def test_shop_non_success_event_quarantines_snapshot_mismatch_without_mutation(
    monkeypatch,
    event_name: str,
    webhook_payload: dict[str, object],
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name=event_name)
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    mocks.active_subscription.return_value = SimpleNamespace(
        subscription_id=501,
        provider="tribute",
        tariff_key="pro",
    )

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(event_name, webhook_payload),
        )
    )

    assert response.status == 400
    assert _response_json(response)["error"] == "snapshot_mismatch"
    assert event.status == "quarantined"
    assert event.payment_id == payment.payment_id
    mocks.update_payment_status.assert_not_awaited()
    mocks.set_auto_renew.assert_not_awaited()
    mocks.ensure_cycle.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("event_name", "extra_field", "extra_value"),
    [
        ("shop_order_charge_failed", "chargeRetries", 3),
        ("shop_order_cancelled", "cancelReason", "cancelled_by_seller"),
    ],
)
def test_shop_recurring_non_success_event_quarantines_period_mismatch(
    monkeypatch,
    event_name: str,
    extra_field: str,
    extra_value: object,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(event_name=event_name)
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )
    webhook_payload = _shop_charge_payload(period="quarterly")
    webhook_payload[extra_field] = extra_value

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(event_name, webhook_payload),
        )
    )

    assert response.status == 400
    assert _response_json(response)["reason"] == "period_mismatch"
    assert event.status == "quarantined"
    mocks.update_payment_status.assert_not_awaited()
    mocks.set_auto_renew.assert_not_awaited()
    mocks.ensure_cycle.assert_not_awaited()
    mocks.claim.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


@pytest.mark.parametrize(
    ("event_name", "webhook_payload"),
    [
        (
            "shop_order",
            {
                **_shop_payload(),
                "uuid": "not-a-uuid",
            },
        ),
        (
            "shop_order",
            {
                **_shop_payload(),
                "amount": "14900",
            },
        ),
        (
            "shop_order",
            {
                **_shop_payload(),
                "currency": "btc",
            },
        ),
        (
            "shop_order",
            {key: value for key, value in _shop_payload().items() if key != "shopId"},
        ),
        (
            "shop_order_charge_failed",
            _shop_charge_payload(),
        ),
        (
            "shop_order_refunded",
            {
                key: value
                for key, value in {
                    **_shop_refund_payload(),
                    "status": "completed",
                }.items()
                if key != "refundedAt"
            },
        ),
    ],
)
def test_shop_webhook_rejects_malformed_wire_payload_before_database_access(
    event_name: str,
    webhook_payload: dict[str, object],
) -> None:
    service = _service()

    response = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(event_name, webhook_payload),
        )
    )

    assert response.status == 400
    assert _response_json(response) == {
        "ok": False,
        "error": "invalid_payload",
    }


def test_shop_recurring_charge_fingerprint_distinguishes_cycle_occurrences(
    monkeypatch,
) -> None:
    session = _FakeSession()
    service = _service(session=session)
    payment = _shop_payment(
        status="succeeded",
        amount=99.0,
        sale_mode="subscription@pro",
        tariff_key="pro",
        months=1,
        purchased_gb=None,
    )
    event = _shop_event(
        status="processed",
        event_name="shop_order_charge_success",
        payment_id=86,
    )
    mocks = _install_shop_mocks(
        monkeypatch,
        service,
        payment=payment,
        event=event,
    )

    first = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(),
                created_at=CREATED_AT,
            ),
        )
    )
    second = asyncio.run(
        service.handle_verified_webhook(
            SimpleNamespace(),
            _verified_event_payload(
                "shop_order_charge_success",
                _shop_charge_payload(),
                created_at=CREATED_AT + timedelta(days=31),
            ),
        )
    )

    assert first.status == second.status == 200
    first_values = mocks.ensure_event.await_args_list[0].args[1]
    second_values = mocks.ensure_event.await_args_list[1].args[1]
    assert first_values["fingerprint"] != second_values["fingerprint"]
    mocks.ensure_cycle.assert_not_awaited()
    mocks.finalize.assert_not_awaited()


def test_shop_descriptor_extracts_uuid_and_prefers_webapp_url() -> None:
    response = {
        "uuid": SHOP_ORDER_UUID,
        "paymentUrl": "https://tribute.tg/shop/pay/order",
        "webappPaymentUrl": "https://t.me/tribute/app?startapp=shop-order",
    }

    assert tribute_service._SHOP_DESCRIPTOR.extract_provider_id(response) == SHOP_ORDER_UUID
    assert tribute_service._SHOP_DESCRIPTOR.extract_url(response) == (
        "https://t.me/tribute/app?startapp=shop-order"
    )
    response["webappPaymentUrl"] = ""
    assert tribute_service._SHOP_DESCRIPTOR.extract_url(response) == (
        "https://tribute.tg/shop/pay/order"
    )
