"""A rejected gateway request is not a failed payer transaction."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.payment_providers.shared import common, webhooks
from bot.services.partner_checkout_balance import PartnerCheckoutBalanceService
from db.dal import payment_dal
from db.models import Payment


@pytest.mark.parametrize("suppress", [True, False])
def test_creation_failure_suppression_is_persisted_with_the_terminal_status(
    monkeypatch: pytest.MonkeyPatch, suppress: bool
) -> None:
    payment = Payment(payment_id=123, user_id=42, status="pending_wata")
    session = AsyncMock()
    session.begin_nested.return_value = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    release = AsyncMock()
    monkeypatch.setattr(
        payment_dal, "get_payment_by_db_id_for_update", AsyncMock(return_value=payment)
    )
    monkeypatch.setattr(PartnerCheckoutBalanceService, "release_if_terminal", release)
    monkeypatch.setattr("bot.services.advertising.capture.record_payment_state", AsyncMock())

    asyncio.run(
        common.mark_payment_failed_creation(
            session,
            123,
            failure_kind="provider_request_rejected",
            failure_http_status=503,
            failure_provider_code="service_unavailable",
            suppress_failure_notification=suppress,
        )
    )

    assert payment.status == "failed_creation"
    assert payment.failure_kind == "provider_request_rejected"
    assert payment.failure_http_status == 503
    assert (payment.failure_notified_at is not None) is suppress
    release.assert_awaited_once_with(session, payment_id=123, status="failed_creation")
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("suppressed", [True, False])
def test_suppressed_attempt_does_not_publish_a_user_failure_notification(
    monkeypatch: pytest.MonkeyPatch, suppressed: bool
) -> None:
    emit = AsyncMock()
    monkeypatch.setattr(webhooks.events, "emit_model", emit)
    payment = Payment(
        payment_id=123,
        user_id=42,
        provider="wata",
        status="failed_creation",
        failure_notified_at=datetime.now(UTC) if suppressed else None,
    )

    asyncio.run(
        webhooks.notify_user_payment_failed(
            bot=None,
            settings=SimpleNamespace(PAYMENT_FAILURE_NOTIFICATION_GRACE_SECONDS=0),
            i18n=None,
            session=AsyncMock(),
            payment=payment,
        )
    )

    assert emit.await_count == (0 if suppressed else 1)
