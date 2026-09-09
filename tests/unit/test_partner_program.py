from __future__ import annotations

import asyncio
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.dml import Delete, Update

from bot.app.web.admin_api_impl.partners import (
    _application_payload,
    _profile_payload,
    _withdrawal_payload,
)
from bot.app.web.partner_schemas import (
    AdminPartnerApplicationOut,
    AdminPartnerWithdrawalOut,
)
from bot.app.web.partner_serialization import withdrawal_out
from bot.services.partner_commission_service import PartnerCommissionService
from bot.services.partner_common import (
    PartnerError,
    amount_to_minor,
    commission_minor,
    minor_to_decimal_string,
)
from bot.services.partner_program_service import PartnerProgramService
from bot.services.partner_withdrawal_service import (
    PartnerWithdrawalService,
    decrypt_partner_requisites,
    encrypt_partner_requisites,
)
from config.settings import Settings
from config.settings_models import (
    PartnerSettings,
    PartnerWithdrawalField,
    PartnerWithdrawalMethod,
    PartnerWithdrawalNetwork,
)
from db.dal.partner_withdrawal_dal import purge_expired_partner_data
from db.models import Payment
from db.partner_models import PartnerProfile, PartnerWithdrawal


@pytest.mark.parametrize(
    ("amount", "scale", "expected"),
    [
        ("12.5", 0, 13),
        ("12.345", 2, 1235),
        ("0.0000005", 6, 1),
        ("999999999999999999.999999", 6, 999999999999999999999999),
    ],
)
def test_partner_minor_units_use_decimal_half_up(
    amount: str,
    scale: int,
    expected: int,
) -> None:
    assert amount_to_minor(amount, scale=scale) == expected
    assert Decimal(minor_to_decimal_string(expected, scale=scale)) == (
        Decimal(expected) / (Decimal(10) ** scale)
    )


@pytest.mark.parametrize(
    ("gross_minor", "bps", "expected"),
    [(1, 5000, 1), (10_001, 3333, 3333), (10**24, 10_000, 10**24), (123, 0, 0)],
)
def test_partner_commission_uses_basis_points_and_half_up(
    gross_minor: int,
    bps: int,
    expected: int,
) -> None:
    assert commission_minor(gross_minor, bps) == expected


def test_partner_requisites_encryption_round_trip_and_wrong_key() -> None:
    old_key = secrets.token_urlsafe(32)
    new_key = secrets.token_urlsafe(32)
    associated_data = b"partner:7:test-request"
    payload = {"card_number": "4111111111111111", "holder": "Test User"}

    ciphertext = encrypt_partner_requisites(
        payload,
        raw_key=old_key,
        associated_data=associated_data,
    )

    assert payload["card_number"].encode() not in ciphertext
    assert (
        decrypt_partner_requisites(
            ciphertext,
            raw_key=old_key,
            associated_data=associated_data,
        )
        == payload
    )
    with pytest.raises(PartnerError, match="withdrawal_requisites_unavailable"):
        decrypt_partner_requisites(
            ciphertext,
            raw_key=new_key,
            associated_data=associated_data,
        )
    with pytest.raises(PartnerError, match="withdrawal_requisites_unavailable"):
        decrypt_partner_requisites(
            ciphertext,
            raw_key=old_key,
            associated_data=b"partner:8:test-request",
        )


def _withdrawal_service() -> PartnerWithdrawalService:
    settings = SimpleNamespace(
        PARTNER_REQUISITES_ENCRYPTION_KEY=SecretStr(secrets.token_urlsafe(32)),
        PARTNER_REQUISITES_KEY_ID="v1",
        partner_settings=PartnerSettings(),
    )
    return PartnerWithdrawalService(settings)  # type: ignore[arg-type]


def test_partner_requisites_are_normalized_and_masked() -> None:
    service = _withdrawal_service()
    card = PartnerWithdrawalMethod(
        id="card",
        type="bank_card",
        label="Card",
        debit_currency="RUB",
        min_amount_minor=10_000,
        fields=[PartnerWithdrawalField(id="card_number")],
    )
    sbp = PartnerWithdrawalMethod(
        id="sbp",
        type="sbp",
        label="SBP",
        debit_currency="RUB",
        min_amount_minor=10_000,
        fields=[PartnerWithdrawalField(id="phone")],
    )
    crypto = PartnerWithdrawalMethod(
        id="usdt",
        type="crypto",
        label="USDT",
        debit_currency="USD",
        min_amount_minor=1000,
        settlement_asset="USDT",
        fields=[PartnerWithdrawalField(id="address")],
        networks=[PartnerWithdrawalNetwork(id="tron", label="TRON")],
    )

    card_values, card_mask = service._validated_requisites(
        card, {"card_number": "4111 1111 1111 1111"}, None
    )
    phone_values, phone_mask = service._validated_requisites(
        sbp, {"phone": "8 (999) 123-45-67"}, None
    )
    crypto_values, crypto_mask = service._validated_requisites(
        crypto, {"address": "TExampleAddress123456789"}, "TRON"
    )

    assert card_values == {"card_number": "4111111111111111"}
    assert card_mask == "•••• 1111"
    assert phone_values == {"phone": "+79991234567"}
    assert phone_mask == "+79••••4567"
    assert crypto_values["network"] == "tron"
    assert crypto_mask == "TRON · ••••23456789"


def test_legacy_crypto_withdrawal_mask_uses_snapshot_network_label_once() -> None:
    withdrawal = cast(
        PartnerWithdrawal,
        SimpleNamespace(
            withdrawal_id=23,
            partner_id=7,
            method_id_snapshot="usdt",
            method_type_snapshot="crypto",
            method_snapshot_json=json.dumps({"networks": [{"id": "network-1", "label": "TON"}]}),
            debit_amount_minor=10_000,
            debit_currency="USD",
            currency_scale=2,
            settlement_asset="USDT",
            network="network-1",
            status="processing",
            status_version=2,
            status_message=None,
            external_reference=None,
            settlement_amount=None,
            masked_requisites="0001…0001 (network-1)",
            requested_at=datetime(2026, 8, 12, tzinfo=UTC),
            processing_at=datetime(2026, 8, 12, tzinfo=UTC),
            paid_at=None,
            decided_at=None,
        ),
    )

    serialized = withdrawal_out(withdrawal)

    assert serialized.masked_requisites == "TON · ••••0001"


@pytest.mark.parametrize(
    "address",
    [
        "EQAbcdefghijklmnopqrstuvwxyz0123456789_-/+=",
        "0:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
    ],
)
def test_crypto_requisites_accept_common_address_alphabets(address: str) -> None:
    service = _withdrawal_service()
    method = PartnerWithdrawalMethod(
        id="crypto",
        type="crypto",
        debit_currency="USD",
        min_amount_minor=100,
        settlement_asset="USDT",
        fields=[PartnerWithdrawalField(id="address")],
        networks=[PartnerWithdrawalNetwork(id="ton", label="TON")],
    )

    values, _ = service._validated_requisites(method, {"address": address}, "TON")

    assert values == {"address": address, "network": "ton"}


@pytest.mark.parametrize("address", ["abc", "wallet address", "wallet\u200baddress"])
def test_crypto_requisites_reject_short_whitespace_or_control_text(address: str) -> None:
    service = _withdrawal_service()
    method = PartnerWithdrawalMethod(
        id="crypto",
        type="crypto",
        debit_currency="USD",
        min_amount_minor=100,
        settlement_asset="USDT",
        fields=[PartnerWithdrawalField(id="address")],
        networks=[PartnerWithdrawalNetwork(id="ton", label="TON")],
    )

    with pytest.raises(PartnerError, match="invalid_crypto_address"):
        service._validated_requisites(method, {"address": address}, "ton")


def test_enabled_withdrawal_method_requires_canonical_field() -> None:
    with pytest.raises(ValidationError, match="card_number"):
        PartnerWithdrawalMethod(
            id="card",
            type="bank_card",
            debit_currency="RUB",
            min_amount_minor=100,
        )


def test_manual_partner_balance_adjustment_allows_empty_description(monkeypatch) -> None:
    profile = SimpleNamespace(partner_id=7)
    entry = SimpleNamespace(entry_id=11, amount_minor=500)
    get_profile = AsyncMock(return_value=profile)
    get_entry = AsyncMock(return_value=None)
    balance_minor = AsyncMock(return_value=1_000)
    create_entry = AsyncMock(return_value=entry)
    create_audit = AsyncMock()
    emit_model = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_commission_service.partner_dal.get_profile_by_id", get_profile
    )
    monkeypatch.setattr(
        "bot.services.partner_commission_service.partner_dal.get_ledger_entry_by_key", get_entry
    )
    monkeypatch.setattr(
        "bot.services.partner_commission_service.partner_dal.balance_minor", balance_minor
    )
    monkeypatch.setattr(
        "bot.services.partner_commission_service.partner_dal.create_ledger_entry", create_entry
    )
    monkeypatch.setattr(
        "bot.services.partner_commission_service.partner_dal.create_audit_event", create_audit
    )
    monkeypatch.setattr("bot.services.partner_commission_service.events.emit_model", emit_model)
    service = PartnerCommissionService(cast(Settings, SimpleNamespace()))

    result = asyncio.run(
        service.adjust_balance(
            AsyncMock(spec=AsyncSession),
            partner_id=7,
            currency="RUB",
            scale=2,
            mode="add",
            amount_minor=500,
            reason=None,
            actor_admin_id=1,
            idempotency_key="balance-test-key",
        )
    )

    assert result == (entry, 1_500)
    entry_call = create_entry.await_args
    audit_call = create_audit.await_args
    assert entry_call is not None
    assert audit_call is not None
    assert entry_call.kwargs["reason"] is None
    assert audit_call.kwargs["reason"] is None


def test_admin_partner_payload_uses_live_user_identity(monkeypatch) -> None:
    now = datetime.now(UTC)
    profile = SimpleNamespace(
        partner_id=7,
        user_id=42,
        display_label_snapshot="Old snapshot",
        status="active",
        commission_bps=3000,
        welcome_message=None,
        pause_reason=None,
        activated_at=now,
        created_at=now,
    )
    monkeypatch.setattr(
        "bot.app.web.admin_api_impl.partners.partner_dal.balance_summaries",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "bot.app.web.admin_api_impl.partners.partner_dal.list_clients",
        AsyncMock(return_value=([], 5)),
    )
    monkeypatch.setattr(
        "bot.app.web.admin_api_impl.partners.partner_dal.profile_currency_metrics",
        AsyncMock(return_value={}),
    )

    payload = asyncio.run(
        _profile_payload(
            AsyncMock(spec=AsyncSession),
            profile,
            user_labels={42: ("alice", "Alice Example")},
            avatar_keys={42: "2026-08-12T12:00:00+00:00"},
        )
    )

    assert payload["display_label"] == "Alice Example"
    assert payload["username"] == "alice"
    assert payload["avatar_url"] == ("/api/admin/users/42/avatar?v=2026-08-12T12:00:00+00:00")
    assert payload["clients_count"] == 5


def test_admin_partner_application_payload_uses_live_user_identity() -> None:
    now = datetime.now(UTC)
    application = SimpleNamespace(
        application_id=12,
        user_id=42,
        display_label_snapshot="Old applicant",
        message="Application text",
        status="pending",
        submitted_at=now,
        decided_at=None,
        decision_message=None,
        approved_commission_bps=None,
        welcome_message=None,
        reapply_allowed_at=None,
    )

    payload = asyncio.run(
        _application_payload(
            AsyncMock(spec=AsyncSession),
            application,
            user_labels={42: ("alice", "Alice Example")},
            avatar_keys={42: "avatar-v1"},
        )
    )

    parsed = AdminPartnerApplicationOut.model_validate(payload)
    assert parsed.display_label == "Alice Example"
    assert parsed.username == "alice"
    assert parsed.avatar_url == "/api/admin/users/42/avatar?v=avatar-v1"


def test_admin_partner_withdrawal_payload_uses_partner_user_identity() -> None:
    now = datetime.now(UTC)
    withdrawal = SimpleNamespace(
        withdrawal_id=23,
        partner_id=7,
        method_id_snapshot="card",
        method_type_snapshot="bank_card",
        method_snapshot_json="{}",
        debit_amount_minor=10_000,
        debit_currency="RUB",
        currency_scale=2,
        settlement_asset=None,
        network=None,
        status="requested",
        status_version=1,
        status_message=None,
        external_reference=None,
        settlement_amount=None,
        masked_requisites="•••• 1111",
        requested_at=now,
        processing_at=None,
        paid_at=None,
        decided_at=None,
    )
    profile = SimpleNamespace(
        partner_id=7,
        user_id=42,
        display_label_snapshot="Old partner",
    )

    payload = asyncio.run(
        _withdrawal_payload(
            AsyncMock(spec=AsyncSession),
            withdrawal,
            profiles_by_id={7: profile},
            user_labels={42: ("alice", "Alice Example")},
            avatar_keys={42: "avatar-v1"},
        )
    )

    parsed = AdminPartnerWithdrawalOut.model_validate(payload)
    assert parsed.user_id == 42
    assert parsed.display_label == "Alice Example"
    assert parsed.username == "alice"
    assert parsed.avatar_url == "/api/admin/users/42/avatar?v=avatar-v1"


def _partner_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "enabled": True,
        "eligible_currencies": ["RUB"],
        "excluded_sale_modes": ["traffic_topup"],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_partner_audit_is_retained_when_retention_is_disabled() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=2)),
    )

    result = asyncio.run(
        purge_expired_partner_data(
            session,
            audit_before=None,
            requisites_before=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    statements = [call.args[0] for call in session.execute.await_args_list]
    assert not any(isinstance(statement, Delete) for statement in statements)
    assert sum(isinstance(statement, Update) for statement in statements) == 1
    assert result == {"audit": 0, "requisites": 2}


def test_partner_audit_is_purged_only_with_an_explicit_cutoff() -> None:
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(rowcount=3),
                SimpleNamespace(rowcount=2),
            ]
        ),
    )

    result = asyncio.run(
        purge_expired_partner_data(
            session,
            audit_before=datetime(2025, 1, 1, tzinfo=UTC),
            requisites_before=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    statements = [call.args[0] for call in session.execute.await_args_list]
    assert sum(isinstance(statement, Delete) for statement in statements) == 1
    assert sum(isinstance(statement, Update) for statement in statements) == 1
    assert result == {"audit": 3, "requisites": 2}


def test_partner_web_link_uses_mini_app_url() -> None:
    service = PartnerProgramService(
        cast(
            Settings,
            SimpleNamespace(
                WEBHOOK_BASE_URL="https://webhooks.website.com",
                SUBSCRIPTION_MINI_APP_URL="https://subdomain.website.com/app?lang=ru#partner",
                partner_settings=_partner_settings(
                    telegram_link_enabled=True,
                    webapp_link_enabled=True,
                ),
            ),
        )
    )

    links = service.links(
        cast(PartnerProfile, SimpleNamespace(partner_code="code")),
        bot_username="@mini_shop_bot",
    )

    assert links["telegram"] == "https://t.me/mini_shop_bot?start=p_code"
    assert links["web"] == ("https://subdomain.website.com/app?lang=ru&partner=code#partner")


def test_partner_web_link_is_unavailable_without_mini_app_url() -> None:
    service = PartnerProgramService(
        cast(
            Settings,
            SimpleNamespace(
                WEBHOOK_BASE_URL="https://webhooks.website.com",
                SUBSCRIPTION_MINI_APP_URL=None,
                partner_settings=_partner_settings(
                    telegram_link_enabled=False,
                    webapp_link_enabled=True,
                ),
            ),
        )
    )

    links = service.links(cast(PartnerProfile, SimpleNamespace(partner_code="code")))

    assert links["web"] is None


def _commission_service(**overrides: object) -> PartnerCommissionService:
    settings = SimpleNamespace(partner_settings=_partner_settings(**overrides))
    return PartnerCommissionService(settings)  # type: ignore[arg-type]


def _payment(**overrides: object) -> Payment:
    values: dict[str, object] = {
        "amount": 100,
        "currency": "RUB",
        "provider": "test",
        "sale_mode": "subscription",
        "funding_source": "external",
    }
    values.update(overrides)
    return Payment(**values)


@pytest.mark.parametrize(
    ("payment", "profile_status", "eligible_from_offset", "expected"),
    [
        (_payment(funding_source="partner_balance"), "active", -1, "internal_funding_source"),
        (_payment(currency="USD"), "active", -1, "currency_not_eligible"),
        (_payment(sale_mode="traffic_topup"), "active", -1, "sale_mode_excluded"),
        (_payment(), "paused", -1, "partner_paused"),
        (_payment(), "active", 1, "before_attribution"),
        (_payment(), "active", -1, None),
    ],
)
def test_partner_commission_exclusion_matrix(
    payment: Payment,
    profile_status: str,
    eligible_from_offset: int,
    expected: str | None,
) -> None:
    paid_at = datetime.now(UTC)
    profile = SimpleNamespace(status=profile_status)
    result = _commission_service()._exclusion_reason(
        payment=payment,
        profile=profile,  # type: ignore[arg-type]
        eligible_from=paid_at + timedelta(seconds=eligible_from_offset),
        source_paid_at=paid_at,
    )
    assert result == expected


def test_partner_attribution_is_first_touch(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = SimpleNamespace(partner_client_id=17, partner_id=3)
    get_existing = AsyncMock(return_value=existing)
    get_profile = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_client_by_user_id",
        get_existing,
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_profile_by_code",
        get_profile,
    )
    service = PartnerProgramService(
        SimpleNamespace(partner_settings=_partner_settings())  # type: ignore[arg-type]
    )

    async def run() -> object:
        return await service.attribute_user(
            AsyncMock(),
            user=SimpleNamespace(user_id=5),  # type: ignore[arg-type]
            partner_code="second-link",
            source="partner_web_link",
        )

    result = asyncio.run(run())

    assert result is existing
    get_profile.assert_not_awaited()


@pytest.mark.parametrize(("enabled", "snapshotted"), [(True, True), (False, False)])
def test_partner_registration_snapshots_welcome_toggle_at_first_touch(
    monkeypatch: pytest.MonkeyPatch,
    enabled: bool,
    snapshotted: bool,
) -> None:
    attribution = SimpleNamespace(
        partner_client_id=17,
        partner_id=3,
        attributed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    create_attribution = AsyncMock(return_value=attribution)
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_client_by_user_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_profile_by_code",
        AsyncMock(
            return_value=SimpleNamespace(
                partner_id=3,
                user_id=9,
                status="active",
            )
        ),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_client_attribution",
        create_attribution,
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_audit_event",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.events.emit_model",
        AsyncMock(),
    )
    service = PartnerProgramService(
        SimpleNamespace(
            partner_settings=_partner_settings(
                client_welcome_bonus_enabled=enabled,
            )
        )
    )
    session = AsyncMock(spec=AsyncSession)
    session.begin_nested.return_value = AsyncMock()
    user = SimpleNamespace(
        user_id=5,
        first_name="Client",
        last_name=None,
        username=None,
        email=None,
    )

    result = asyncio.run(
        service.attribute_user(
            session,
            user=user,
            partner_code="first-link",
            source="partner_web_link",
            registered_via_partner_link=True,
        )
    )

    assert result is attribution
    create_call = create_attribution.await_args
    assert create_call is not None
    eligible_at = create_call.kwargs["welcome_bonus_eligible_at"]
    assert (eligible_at is not None) is snapshotted


@pytest.mark.parametrize(
    ("eligible_at", "profile_status", "expected"),
    [
        (datetime(2026, 1, 1, tzinfo=UTC), "active", True),
        (None, "active", False),
        (datetime(2026, 1, 1, tzinfo=UTC), "paused", False),
    ],
)
def test_partner_welcome_bonus_requires_registration_snapshot_and_active_profile(
    monkeypatch: pytest.MonkeyPatch,
    eligible_at: datetime | None,
    profile_status: str,
    expected: bool,
) -> None:
    get_attribution = AsyncMock(
        return_value=(
            SimpleNamespace(
                source="partner_web_link",
                welcome_bonus_eligible_at=eligible_at,
            ),
            SimpleNamespace(status=profile_status),
        )
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_client_with_profile_for_user",
        get_attribution,
    )
    service = PartnerProgramService(
        SimpleNamespace(
            partner_settings=_partner_settings(
                client_welcome_bonus_enabled=True,
            )
        )
    )

    result = asyncio.run(
        service.client_welcome_bonus_eligible(
            AsyncMock(),
            user_id=5,
        )
    )

    assert result is expected


def test_partner_client_benefits_stay_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    get_attribution = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_client_with_profile_for_user",
        get_attribution,
    )
    service = PartnerProgramService(
        cast(Settings, SimpleNamespace(partner_settings=PartnerSettings(enabled=True)))
    )

    welcome = asyncio.run(
        service.client_welcome_bonus_eligible(
            AsyncMock(),
            user_id=5,
        )
    )
    payment = asyncio.run(
        service.client_payment_bonus_eligible(
            AsyncMock(),
            user_id=5,
        )
    )

    assert welcome is False
    assert payment is False
    get_attribution.assert_not_awaited()


@pytest.mark.parametrize(
    (
        "referral_enabled",
        "program_enabled",
        "referrals_disabled",
        "profile",
        "expected",
        "queried",
    ),
    [
        (False, False, False, None, False, False),
        (True, False, True, SimpleNamespace(status="active"), True, False),
        (True, True, False, SimpleNamespace(status="active"), True, False),
        (True, True, True, None, True, True),
        (True, True, True, SimpleNamespace(status="active"), False, True),
        (True, True, True, SimpleNamespace(status="paused"), False, True),
        (True, True, True, SimpleNamespace(status="closed"), False, True),
    ],
)
def test_partner_profile_controls_referral_program_visibility(
    monkeypatch: pytest.MonkeyPatch,
    referral_enabled: bool,
    program_enabled: bool,
    referrals_disabled: bool,
    profile: object | None,
    expected: bool,
    queried: bool,
) -> None:
    get_profile = AsyncMock(return_value=profile)
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_profile_by_user_id",
        get_profile,
    )
    service = PartnerProgramService(
        SimpleNamespace(
            REFERRAL_PROGRAM_ENABLED=referral_enabled,
            referral_settings=SimpleNamespace(enabled=referral_enabled),
            partner_settings=_partner_settings(
                enabled=program_enabled,
                referral_program_disabled=referrals_disabled,
            ),
        )  # type: ignore[arg-type]
    )

    result = asyncio.run(
        service.referral_program_enabled_for_user(
            AsyncMock(),
            user_id=5,
        )
    )

    assert result is expected
    if queried:
        get_profile.assert_awaited_once()
    else:
        get_profile.assert_not_awaited()


def test_automatic_partner_enrollment_batches_existing_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    users = [
        SimpleNamespace(
            user_id=5,
            is_banned=False,
            first_name="Alice",
            last_name=None,
            username="alice",
            email=None,
        ),
        SimpleNamespace(
            user_id=6,
            is_banned=False,
            first_name=None,
            last_name=None,
            username=None,
            email="bo@example.test",
        ),
    ]
    list_users = AsyncMock(side_effect=[users, []])
    create_profiles = AsyncMock(return_value={5: 15, 6: 16})
    approve_pending = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.list_users_without_partner_profile",
        list_users,
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_profiles_bulk",
        create_profiles,
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.approve_pending_applications_for_users",
        approve_pending,
    )
    service = PartnerProgramService(
        SimpleNamespace(
            partner_settings=_partner_settings(
                auto_enrollment_enabled=True,
                default_commission_bps=2500,
            )
        )  # type: ignore[arg-type]
    )

    enrolled = asyncio.run(
        service.auto_enroll_all_users(
            AsyncMock(spec=AsyncSession),
            actor_admin_id=7,
        )
    )

    assert enrolled == 2
    assert list_users.await_count == 2
    create_call = create_profiles.await_args
    assert create_call is not None
    payloads = create_call.kwargs["profiles"]
    assert [payload["user_id"] for payload in payloads] == [5, 6]
    assert [payload["commission_bps"] for payload in payloads] == [2500, 2500]
    assert [payload["display_label_snapshot"] for payload in payloads] == [
        "Alice",
        "bo***@example.test",
    ]
    assert len({payload["partner_code"] for payload in payloads}) == 2
    assert create_call.kwargs["actor_user_id"] == 7
    approve_pending.assert_awaited_once()
    approve_call = approve_pending.await_args
    assert approve_call is not None
    assert approve_call.kwargs == {
        "user_ids": [5, 6],
        "actor_user_id": 7,
    }


def test_automatic_partner_enrollment_preserves_paused_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(partner_id=15, user_id=5, status="paused")
    get_profile = AsyncMock(return_value=profile)
    approve_pending = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_profile_by_user_id",
        get_profile,
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.approve_pending_applications_for_users",
        approve_pending,
    )
    service = PartnerProgramService(
        SimpleNamespace(partner_settings=_partner_settings(auto_enrollment_enabled=True))  # type: ignore[arg-type]
    )
    user = SimpleNamespace(user_id=5, is_banned=False)

    result = asyncio.run(
        service.auto_enroll_user(
            AsyncMock(spec=AsyncSession),
            user=user,  # type: ignore[arg-type]
        )
    )

    assert result is profile
    approve_pending.assert_not_awaited()


def test_automatic_partner_enrollment_rejects_new_applications() -> None:
    service = PartnerProgramService(
        SimpleNamespace(partner_settings=_partner_settings(auto_enrollment_enabled=True))  # type: ignore[arg-type]
    )

    with pytest.raises(PartnerError, match="partner_application_not_required"):
        asyncio.run(
            service.submit_application(
                AsyncMock(spec=AsyncSession),
                user_id=5,
                message="A valid application message",
            )
        )


@pytest.mark.parametrize(("application_id", "emitted"), [(None, True), (17, False)])
def test_direct_partner_activation_emits_status_event_once(
    monkeypatch: pytest.MonkeyPatch,
    application_id: int | None,
    emitted: bool,
) -> None:
    activated_at = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    profile = SimpleNamespace(
        partner_id=8,
        user_id=42,
        status="active",
        commission_bps=3000,
        activated_at=activated_at,
    )
    emit_model = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_profile_by_user_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_profile",
        AsyncMock(return_value=profile),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_audit_event",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.events.emit_model",
        emit_model,
    )
    service = PartnerProgramService(
        SimpleNamespace(
            partner_settings=_partner_settings(default_commission_bps=3000),
        )  # type: ignore[arg-type]
    )
    session = AsyncMock(spec=AsyncSession)
    session.begin_nested.return_value = AsyncMock()
    user = SimpleNamespace(
        user_id=42,
        first_name="Alice",
        last_name=None,
        username="alice",
        email=None,
    )

    asyncio.run(
        service.create_profile_for_user(
            session,
            user=user,  # type: ignore[arg-type]
            actor_admin_id=1,
            application_id=application_id,
        )
    )

    if emitted:
        emit_model.assert_awaited_once()
        emit_call = emit_model.await_args
        assert emit_call is not None
        payload = emit_call.args[0]
        assert payload.partner_id == 8
        assert payload.user_id == 42
        assert payload.old_status == "none"
        assert payload.status == "active"
        assert payload.changed_at == activated_at
    else:
        emit_model.assert_not_awaited()


def test_partner_self_attribution_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_client_by_user_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.get_profile_by_code",
        AsyncMock(
            return_value=SimpleNamespace(
                partner_id=9,
                user_id=5,
                status="active",
            )
        ),
    )
    service = PartnerProgramService(
        SimpleNamespace(partner_settings=_partner_settings())  # type: ignore[arg-type]
    )

    async def run() -> object:
        return await service.attribute_user(
            AsyncMock(),
            user=SimpleNamespace(user_id=5),  # type: ignore[arg-type]
            partner_code="own-link",
            source="partner_telegram_link",
        )

    with pytest.raises(PartnerError, match="partner_self_attribution"):
        asyncio.run(run())


def test_all_referrals_import_preview_counts_every_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_partner = SimpleNamespace(partner_id=1, user_id=10)
    second_partner = SimpleNamespace(partner_id=2, user_id=20)
    candidates = [
        (first_partner, SimpleNamespace(user_id=11), None, 2),
        (
            first_partner,
            SimpleNamespace(user_id=12),
            SimpleNamespace(partner_id=1),
            1,
        ),
        (
            first_partner,
            SimpleNamespace(user_id=13),
            SimpleNamespace(partner_id=2),
            3,
        ),
        (second_partner, SimpleNamespace(user_id=20), None, 0),
    ]
    list_candidates = AsyncMock(return_value=candidates)
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_reporting_dal.all_referral_import_candidates",
        list_candidates,
    )
    service = PartnerProgramService(cast(Settings, SimpleNamespace(REFERRAL_PROGRAM_ENABLED=False)))

    result = asyncio.run(service.bulk_referral_import_preview(AsyncMock()))

    assert result == {
        "partners": 2,
        "found": 4,
        "importable": 1,
        "already_this_partner": 1,
        "other_partner": 1,
        "self_conflict": 1,
        "historical_payments": 6,
    }
    list_candidates.assert_awaited_once()


def test_all_referrals_import_requires_disabled_referral_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    list_candidates = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_reporting_dal.all_referral_import_candidates",
        list_candidates,
    )
    service = PartnerProgramService(cast(Settings, SimpleNamespace(REFERRAL_PROGRAM_ENABLED=True)))

    with pytest.raises(PartnerError, match="referral_program_enabled"):
        asyncio.run(service.bulk_referral_import_preview(AsyncMock()))

    list_candidates.assert_not_awaited()


def test_execute_all_referrals_import_creates_clients_and_partner_audits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_partner = SimpleNamespace(partner_id=1, user_id=10)
    second_partner = SimpleNamespace(partner_id=2, user_id=20)
    candidates = [
        (
            first_partner,
            SimpleNamespace(
                user_id=11,
                first_name="First",
                last_name=None,
                username=None,
                email=None,
            ),
            None,
            0,
        ),
        (
            first_partner,
            SimpleNamespace(user_id=12),
            SimpleNamespace(partner_id=1),
            0,
        ),
        (
            first_partner,
            SimpleNamespace(user_id=13),
            SimpleNamespace(partner_id=2),
            0,
        ),
        (
            second_partner,
            SimpleNamespace(
                user_id=21,
                first_name="Second",
                last_name=None,
                username=None,
                email=None,
            ),
            None,
            0,
        ),
    ]
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_reporting_dal.all_referral_import_candidates",
        AsyncMock(return_value=candidates),
    )
    create_attributions = AsyncMock(return_value={11: 1, 21: 2})
    create_audit = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_client_attributions_bulk",
        create_attributions,
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_audit_event",
        create_audit,
    )
    service = PartnerProgramService(cast(Settings, SimpleNamespace(REFERRAL_PROGRAM_ENABLED=False)))
    session = AsyncMock(spec=AsyncSession)

    result = asyncio.run(
        service.execute_bulk_referral_import(
            session,
            actor_admin_id=99,
        )
    )

    assert result == {
        "partners_updated": 2,
        "imported": 2,
        "existing": 1,
        "conflicts": 1,
    }
    create_attributions.assert_awaited_once()
    create_attributions_call = create_attributions.await_args
    assert create_attributions_call is not None
    clients = create_attributions_call.kwargs["clients"]
    assert {client["client_user_id"] for client in clients} == {11, 21}
    assert {client["partner_id"] for client in clients} == {1, 2}
    assert create_audit.await_count == 2
    assert {call.kwargs["partner_id"] for call in create_audit.await_args_list} == {1, 2}


def test_execute_all_referrals_import_counts_concurrent_bulk_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(partner_id=1, user_id=10)
    candidates = [
        (
            profile,
            SimpleNamespace(
                user_id=user_id,
                first_name=f"Client {user_id}",
                last_name=None,
                username=None,
                email=None,
            ),
            None,
            0,
        )
        for user_id in (11, 12)
    ]
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_reporting_dal.all_referral_import_candidates",
        AsyncMock(return_value=candidates),
    )
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_client_attributions_bulk",
        AsyncMock(return_value={11: 1}),
    )
    create_audit = AsyncMock()
    monkeypatch.setattr(
        "bot.services.partner_program_service.partner_dal.create_audit_event",
        create_audit,
    )
    service = PartnerProgramService(cast(Settings, SimpleNamespace(REFERRAL_PROGRAM_ENABLED=False)))

    result = asyncio.run(
        service.execute_bulk_referral_import(
            AsyncMock(spec=AsyncSession),
            actor_admin_id=99,
        )
    )

    assert result == {
        "partners_updated": 1,
        "imported": 1,
        "existing": 0,
        "conflicts": 1,
    }
    create_audit.assert_awaited_once()
    create_audit_call = create_audit.await_args
    assert create_audit_call is not None
    assert json.loads(create_audit_call.kwargs["new_values_json"]) == {
        "bulk": True,
        "conflicts": 1,
        "existing": 0,
        "imported": 1,
    }
