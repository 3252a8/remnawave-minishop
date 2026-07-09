from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from bot.infra import event_payloads, events
from bot.infra.event_payloads import (
    AccountEmailLinkedPayload,
    AccountMergedPayload,
    AccountTelegramLinkedPayload,
    BotStartedPayload,
    PanelWebhookReceivedPayload,
    PaymentCanceledPayload,
    PaymentSucceededPayload,
    PlansViewedPayload,
    PromoCodeAppliedPayload,
    ReferralBonusGrantedPayload,
    SubscriptionCreatedPayload,
    SubscriptionExtendedPayload,
    SupportTicketCreatedPayload,
    TrialActivatedPayload,
    UserRegisteredPayload,
)

UTC_DT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
UTC_TEXT = "2026-01-02T03:04:05+00:00"


@pytest.mark.parametrize(
    ("model_cls", "event_name"),
    [
        (PaymentSucceededPayload, events.PAYMENT_SUCCEEDED),
        (PaymentCanceledPayload, events.PAYMENT_CANCELED),
        (SubscriptionCreatedPayload, events.SUBSCRIPTION_CREATED),
        (SubscriptionExtendedPayload, events.SUBSCRIPTION_EXTENDED),
        (TrialActivatedPayload, events.TRIAL_ACTIVATED),
        (PlansViewedPayload, events.PLANS_VIEWED),
        (BotStartedPayload, events.BOT_STARTED),
        (UserRegisteredPayload, events.USER_REGISTERED),
        (AccountEmailLinkedPayload, events.ACCOUNT_EMAIL_LINKED),
        (AccountTelegramLinkedPayload, events.ACCOUNT_TELEGRAM_LINKED),
        (AccountMergedPayload, events.ACCOUNT_MERGED),
        (PromoCodeAppliedPayload, events.PROMO_CODE_APPLIED),
        (ReferralBonusGrantedPayload, events.REFERRAL_BONUS_GRANTED),
        (SupportTicketCreatedPayload, events.SUPPORT_TICKET_CREATED),
        (PanelWebhookReceivedPayload, events.PANEL_WEBHOOK_RECEIVED),
    ],
)
def test_event_payload_names_match_bus_constants(model_cls, event_name):
    assert event_name == model_cls.EVENT_NAME


def test_every_event_constant_has_exactly_one_payload_model():
    event_names = {
        value for name, value in vars(events).items() if name.isupper() and isinstance(value, str)
    }
    model_event_names = [
        model.EVENT_NAME
        for model in vars(event_payloads).values()
        if isinstance(model, type)
        and issubclass(model, event_payloads.EventPayload)
        and model is not event_payloads.EventPayload
    ]

    duplicate_model_names = {
        event_name for event_name in model_event_names if model_event_names.count(event_name) > 1
    }
    assert duplicate_model_names == set()
    assert set(model_event_names) == event_names


def test_emit_model_preserves_public_subscriber_signature():
    received = []

    async def handler(event_name, payload):
        received.append((event_name, payload))

    events.reset_subscribers()
    events.subscribe(events.TRIAL_ACTIVATED, handler)
    try:
        asyncio.run(
            events.emit_model(
                TrialActivatedPayload(
                    user_id=42,
                    end_date=UTC_DT,
                    days=7,
                    traffic_gb=12.5,
                )
            )
        )
    finally:
        events.reset_subscribers()

    assert received == [
        (
            events.TRIAL_ACTIVATED,
            {
                "user_id": 42,
                "end_date": UTC_TEXT,
                "days": 7,
                "traffic_gb": 12.5,
            },
        )
    ]


def test_event_payloads_reject_extra_keys():
    with pytest.raises(ValidationError):
        TrialActivatedPayload(
            user_id=42,
            end_date=UTC_DT,
            days=7,
            traffic_gb=12.5,
            typo=True,
        )


def test_payment_succeeded_payload_matches_legacy_wire_dict():
    payload = PaymentSucceededPayload(
        user_id=42,
        payment_db_id=5,
        provider="yookassa",
        notification_provider="yookassa",
        amount=180.0,
        currency="RUB",
        sale_mode="subscription@standard",
        tariff_key="standard",
        months=1,
        traffic_gb=None,
        purchased_hwid_devices=2,
        end_date=UTC_DT,
        is_auto_renew=False,
    ).to_payload()

    assert payload == {
        "user_id": 42,
        "payment_db_id": 5,
        "provider": "yookassa",
        "notification_provider": "yookassa",
        "amount": 180.0,
        "base_amount": None,
        "discount_amount": None,
        "currency": "RUB",
        "promo_code_id": None,
        "sale_mode": "subscription@standard",
        "tariff_key": "standard",
        "months": 1,
        "traffic_gb": None,
        "purchased_hwid_devices": 2,
        "end_date": UTC_TEXT,
        "is_auto_renew": False,
    }


def test_payment_canceled_payload_preserves_sparse_yookassa_wire_dict():
    payload = PaymentCanceledPayload(
        user_id=42,
        payment_db_id=5,
        provider="yookassa",
        provider_payment_id="yk_1",
        status="canceled",
    ).to_payload(exclude_unset=True)

    assert payload == {
        "user_id": 42,
        "payment_db_id": 5,
        "provider": "yookassa",
        "provider_payment_id": "yk_1",
        "status": "canceled",
    }


def test_subscription_payloads_match_legacy_wire_dicts():
    expected = {
        "user_id": 42,
        "subscription_id": 7,
        "tariff_key": "standard",
        "end_date": UTC_TEXT,
        "provider": "yookassa",
        "months": 1,
        "payment_db_id": 5,
    }

    assert (
        SubscriptionCreatedPayload(
            user_id=42,
            subscription_id=7,
            tariff_key="standard",
            end_date=UTC_DT,
            provider="yookassa",
            months=1,
            payment_db_id=5,
        ).to_payload()
        == expected
    )
    assert (
        SubscriptionExtendedPayload(
            user_id=42,
            subscription_id=7,
            tariff_key="standard",
            end_date=UTC_DT,
            provider="yookassa",
            months=1,
            payment_db_id=5,
        ).to_payload()
        == expected
    )


def test_registration_and_account_payloads_match_legacy_wire_dicts():
    assert UserRegisteredPayload(
        user_id=42,
        language="ru",
        referred_by_id=7,
        registered_via="telegram",
        telegram_id=100,
        username="neo",
        first_name="Neo",
        email=None,
    ).to_payload() == {
        "user_id": 42,
        "telegram_id": 100,
        "username": "neo",
        "first_name": "Neo",
        "email": None,
        "language": "ru",
        "referred_by_id": 7,
        "registered_via": "telegram",
    }
    assert AccountEmailLinkedPayload(
        user_id=42,
        email="u@example.test",
        first_link=True,
        telegram_id=100,
        username="neo",
        first_name="Neo",
    ).to_payload() == {
        "user_id": 42,
        "email": "u@example.test",
        "first_link": True,
        "telegram_id": 100,
        "username": "neo",
        "first_name": "Neo",
    }
    assert AccountTelegramLinkedPayload(
        user_id=42,
        telegram_id=100,
        first_link=True,
        email="u@example.test",
        username="neo",
        first_name="Neo",
    ).to_payload() == {
        "user_id": 42,
        "telegram_id": 100,
        "first_link": True,
        "email": "u@example.test",
        "username": "neo",
        "first_name": "Neo",
    }


def test_account_merged_payload_matches_legacy_wire_dict():
    assert AccountMergedPayload(
        source_user_id=1,
        target_user_id=2,
        reason="email_link",
        send_user_email=True,
        source_panel_user_uuid="old",
        target_panel_user_uuid="new",
        email="u@example.test",
        telegram_id=100,
        username="neo",
        first_name="Neo",
        language="ru",
        final_end_date=UTC_DT,
    ).to_payload() == {
        "source_user_id": 1,
        "target_user_id": 2,
        "reason": "email_link",
        "send_user_email": True,
        "source_panel_user_uuid": "old",
        "target_panel_user_uuid": "new",
        "email": "u@example.test",
        "telegram_id": 100,
        "username": "neo",
        "first_name": "Neo",
        "language": "ru",
        "final_end_date": UTC_TEXT,
    }


def test_small_event_payloads_match_legacy_wire_dicts():
    assert TrialActivatedPayload(
        user_id=42,
        end_date=UTC_DT,
        days=7,
        traffic_gb=12.5,
    ).to_payload() == {
        "user_id": 42,
        "end_date": UTC_TEXT,
        "days": 7,
        "traffic_gb": 12.5,
    }
    assert PromoCodeAppliedPayload(
        user_id=42,
        code="GIFT",
        bonus_days=7,
        new_end_date=UTC_DT,
    ).to_payload() == {
        "user_id": 42,
        "code": "GIFT",
        "bonus_days": 7,
        "new_end_date": UTC_TEXT,
    }
    assert SupportTicketCreatedPayload(
        user_id=42,
        ticket_id=9,
        category="billing",
        priority="normal",
    ).to_payload() == {
        "user_id": 42,
        "ticket_id": 9,
        "category": "billing",
        "priority": "normal",
    }
    assert PanelWebhookReceivedPayload(
        event="user.expired",
        panel_user_uuid="abc",
        telegram_id=42,
    ).to_payload() == {
        "event": "user.expired",
        "panel_user_uuid": "abc",
        "telegram_id": 42,
    }


def test_referral_payment_payload_matches_legacy_wire_dict():
    assert ReferralBonusGrantedPayload(
        referee_user_id=42,
        referee_bonus_days=3,
        referee_new_end_date=UTC_DT,
        inviter_bonus_applied=True,
        inviter_user_id=7,
        inviter_bonus_days=5,
        inviter_bonus_end_date=UTC_DT,
        inviter_bonus_kind="extended",
        referee_name="Neo",
        payment_db_id=5,
        purchased_subscription_months=1,
        tariff_key="standard",
        one_bonus_per_referee=True,
        reason="payment",
    ).to_payload() == {
        "referee_user_id": 42,
        "referee_bonus_days": 3,
        "referee_new_end_date": UTC_TEXT,
        "inviter_bonus_applied": True,
        "inviter_user_id": 7,
        "inviter_bonus_days": 5,
        "inviter_bonus_end_date": UTC_TEXT,
        "inviter_bonus_kind": "extended",
        "referee_name": "Neo",
        "payment_db_id": 5,
        "purchased_subscription_months": 1,
        "tariff_key": "standard",
        "one_bonus_per_referee": True,
        "reason": "payment",
    }


def test_referral_welcome_payload_preserves_sparse_legacy_wire_dict():
    payload = ReferralBonusGrantedPayload(
        referee_user_id=42,
        referee_bonus_days=3,
        referee_new_end_date=UTC_DT,
        inviter_bonus_applied=False,
        payment_db_id=None,
        reason="welcome",
    ).to_payload(exclude_unset=True)

    assert payload == {
        "referee_user_id": 42,
        "referee_bonus_days": 3,
        "referee_new_end_date": UTC_TEXT,
        "inviter_bonus_applied": False,
        "payment_db_id": None,
        "reason": "welcome",
    }
