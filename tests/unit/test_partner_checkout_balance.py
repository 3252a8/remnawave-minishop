import json
from types import SimpleNamespace
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.webapp import billing_partner_checkout
from bot.payment_providers.base import WebAppPaymentContext
from bot.payment_providers.shared.common import create_base_payment_record
from bot.services.partner_checkout_balance import (
    PartnerCheckoutBalanceAllocation,
    PartnerCheckoutBalanceService,
)
from bot.services.partner_program_worker import PartnerProgramWorker
from bot.services.user_balance_service import UserBalanceService
from config.settings import Settings


class PartnerCheckoutBalanceQuoteTests(IsolatedAsyncioTestCase):
    async def test_quote_uses_partial_balance_and_preserves_provider_minimum(self) -> None:
        service = PartnerCheckoutBalanceService(
            cast(
                Settings,
                SimpleNamespace(
                    partner_settings=SimpleNamespace(
                        enabled=True,
                        balance_payment_enabled=True,
                    )
                ),
            )
        )
        session = cast(AsyncSession, object())

        with (
            patch(
                "bot.services.partner_checkout_balance.partner_dal.get_profile_by_user_id",
                AsyncMock(return_value=SimpleNamespace(partner_id=7, status="active")),
            ),
            patch(
                "bot.services.partner_checkout_balance.partner_dal.balance_minor",
                AsyncMock(return_value=18000),
            ),
        ):
            allocation = await service.quote(
                session,
                user_id=42,
                currency="RUB",
                checkout_total=190,
                minimum_external_amount=50,
            )

        self.assertEqual(allocation.checkout_total_minor, 19000)
        self.assertEqual(allocation.applied_minor, 14000)
        self.assertEqual(allocation.external_minor, 5000)
        self.assertEqual(allocation.external_amount, 50.0)

    async def test_quote_skips_provider_minimum_when_balance_covers_checkout(self) -> None:
        service = PartnerCheckoutBalanceService(
            cast(
                Settings,
                SimpleNamespace(
                    partner_settings=SimpleNamespace(
                        enabled=True,
                        balance_payment_enabled=True,
                    )
                ),
            )
        )

        with (
            patch(
                "bot.services.partner_checkout_balance.partner_dal.get_profile_by_user_id",
                AsyncMock(return_value=SimpleNamespace(partner_id=7, status="active")),
            ),
            patch(
                "bot.services.partner_checkout_balance.partner_dal.balance_minor",
                AsyncMock(return_value=20000),
            ),
        ):
            allocation = await service.quote(
                cast(AsyncSession, object()),
                user_id=42,
                currency="RUB",
                checkout_total=190,
                minimum_external_amount=500,
            )

        self.assertEqual(allocation.applied_minor, 19000)
        self.assertEqual(allocation.external_minor, 0)


class PartnerCheckoutBalanceLifecycleTests(IsolatedAsyncioTestCase):
    async def test_payment_record_and_balance_reservation_commit_together(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        payment = SimpleNamespace(payment_id=17)
        create_payment = AsyncMock(return_value=payment)
        reserve = AsyncMock()

        with (
            patch(
                "bot.payment_providers.shared.common.payment_dal.create_payment_record",
                create_payment,
            ),
            patch.object(PartnerCheckoutBalanceService, "reserve", reserve),
        ):
            result = await create_base_payment_record(
                session,
                user_id=42,
                amount=50.0,
                currency="RUB",
                status="pending",
                description="Mixed checkout",
                months=1,
                provider="card",
                checkout_total_amount=190.0,
                partner_balance_partner_id=7,
                partner_balance_amount_minor=14000,
                partner_balance_currency_scale=2,
            )

        self.assertIs(result, payment)
        create_payment_call = create_payment.await_args
        self.assertIsNotNone(create_payment_call)
        assert create_payment_call is not None
        payload = create_payment_call.args[1]
        self.assertEqual(payload["amount"], 50.0)
        self.assertEqual(payload["checkout_total_amount"], 190.0)
        self.assertEqual(payload["partner_balance_amount_minor"], 14000)
        reserve.assert_awaited_once()
        reserve_call = reserve.await_args
        self.assertIsNotNone(reserve_call)
        assert reserve_call is not None
        allocation = reserve_call.kwargs["allocation"]
        self.assertEqual(allocation.checkout_total_minor, 19000)
        self.assertEqual(allocation.applied_minor, 14000)
        session.commit.assert_awaited_once()

    async def test_delayed_success_voids_release_and_refund_reposts_it(self) -> None:
        release = SimpleNamespace(
            partner_id=7,
            state="posted",
            reason="checkout payment failed_creation",
        )
        profile_lookup = AsyncMock(return_value=SimpleNamespace(partner_id=7))

        with (
            patch(
                "bot.services.partner_checkout_balance.partner_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=release),
            ),
            patch(
                "bot.services.partner_checkout_balance.partner_dal.get_profile_by_id",
                profile_lookup,
            ),
        ):
            result = await PartnerCheckoutBalanceService.ensure_consumed(
                cast(AsyncSession, object()),
                payment_id=17,
            )

        self.assertIs(result, release)
        self.assertEqual(release.state, "void")
        self.assertIn("completed", release.reason)

        spend = SimpleNamespace(partner_id=7)
        ledger_lookup = AsyncMock(side_effect=[spend, release])
        with (
            patch(
                "bot.services.partner_checkout_balance.partner_dal.get_ledger_entry_by_key",
                ledger_lookup,
            ),
            patch(
                "bot.services.partner_checkout_balance.partner_dal.get_profile_by_id",
                profile_lookup,
            ),
        ):
            result = await PartnerCheckoutBalanceService.release(
                cast(AsyncSession, object()),
                payment_id=17,
                reason="checkout payment refunded",
            )

        self.assertIs(result, release)
        self.assertEqual(release.state, "posted")
        self.assertEqual(release.reason, "checkout payment refunded")

    async def test_worker_releases_stale_fully_funded_checkout(self) -> None:
        payment = SimpleNamespace(
            payment_id=17,
            status="succeeded_pending_finalization",
            updated_at=None,
        )
        list_stale = AsyncMock(return_value=[payment])
        release = AsyncMock()
        session = object()
        worker = PartnerProgramWorker(
            cast(Settings, SimpleNamespace()),
            cast(object, SimpleNamespace()),
        )

        with (
            patch(
                "bot.services.partner_program_worker.partner_checkout_dal."
                "list_stale_partner_checkout_payments",
                list_stale,
            ),
            patch(
                "bot.services.partner_program_worker.user_balance_dal.list_stale_checkout_payments",
                AsyncMock(return_value=[]),
            ),
            patch.object(PartnerCheckoutBalanceService, "release", release),
        ):
            recovered = await worker._recover_stale_checkout_spends(session)

        self.assertEqual(recovered, 1)
        release.assert_awaited_once_with(
            session,
            payment_id=17,
            reason="partner-funded checkout finalization timed out",
        )
        self.assertEqual(payment.status, "activation_failed")
        self.assertIsNotNone(payment.updated_at)

    async def test_worker_releases_stale_user_balance_checkout(self) -> None:
        payment = SimpleNamespace(
            payment_id=18,
            status="succeeded_pending_finalization",
            updated_at=None,
        )
        session = object()
        worker = PartnerProgramWorker(
            cast(Settings, SimpleNamespace()),
            cast(object, SimpleNamespace()),
        )
        release = AsyncMock()

        with (
            patch(
                "bot.services.partner_program_worker.partner_checkout_dal."
                "list_stale_partner_checkout_payments",
                AsyncMock(return_value=[]),
            ),
            patch(
                "bot.services.partner_program_worker.user_balance_dal.list_stale_checkout_payments",
                AsyncMock(return_value=[payment]),
            ),
            patch.object(UserBalanceService, "release", release),
        ):
            recovered = await worker._recover_stale_checkout_spends(session)

        self.assertEqual(recovered, 1)
        release.assert_awaited_once_with(
            session,
            payment_id=18,
            reason="user-balance-funded checkout finalization timed out",
        )
        self.assertEqual(payment.status, "activation_failed")
        self.assertIsNotNone(payment.updated_at)

    async def test_worker_releases_terminal_user_balance_checkout(self) -> None:
        payment = SimpleNamespace(payment_id=19, status="refunded")
        session = object()
        worker = PartnerProgramWorker(
            cast(Settings, SimpleNamespace()),
            cast(object, SimpleNamespace()),
        )
        release = AsyncMock()

        with (
            patch(
                "bot.services.partner_program_worker.partner_checkout_dal."
                "list_terminal_partner_checkout_payments",
                AsyncMock(return_value=[]),
            ),
            patch(
                "bot.services.partner_program_worker.user_balance_dal."
                "list_terminal_checkout_payments",
                AsyncMock(return_value=[payment]),
            ),
            patch.object(UserBalanceService, "release_if_terminal", release),
        ):
            recovered = await worker._release_terminal_checkout_spends(session)

        self.assertEqual(recovered, 1)
        release.assert_awaited_once_with(
            session,
            payment_id=19,
            status="refunded",
        )

    async def test_fully_funded_checkout_uses_common_finalizer(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        payment = SimpleNamespace(payment_id=17)
        context = WebAppPaymentContext(
            request=object(),
            session=session,
            user_id=42,
            method="card",
            months=1,
            price=0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@basic",
        )
        allocation = PartnerCheckoutBalanceAllocation(
            partner_id=7,
            currency="RUB",
            currency_scale=2,
            checkout_total_minor=19000,
            applied_minor=19000,
        )
        create_record = AsyncMock(return_value=payment)
        finalize = AsyncMock(return_value=SimpleNamespace())

        with (
            patch.object(
                billing_partner_checkout,
                "create_webapp_payment_record",
                create_record,
            ),
            patch.object(
                billing_partner_checkout,
                "get_referral_service",
                return_value=object(),
            ),
            patch.object(billing_partner_checkout, "get_bot", return_value=object()),
            patch.object(billing_partner_checkout, "get_settings", return_value=object()),
            patch.object(billing_partner_checkout, "get_i18n", return_value=object()),
            patch.object(
                billing_partner_checkout,
                "get_subscription_service",
                return_value=object(),
            ),
            patch.object(billing_partner_checkout, "finalize_successful_payment", finalize),
        ):
            response = await billing_partner_checkout.create_fully_partner_funded_payment(
                request=cast(web.Request, context.request),
                payment_context=context,
                allocation=allocation,
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.text)["action"], "completed")
        create_record.assert_awaited_once_with(
            context,
            amount=190.0,
            currency="RUB",
            status="succeeded_pending_finalization",
            provider="partner_balance",
            funding_source="internal_partner_balance",
        )
        finalize_call = finalize.await_args
        self.assertIsNotNone(finalize_call)
        assert finalize_call is not None
        request = finalize_call.args[0]
        self.assertTrue(request.skip_referral_bonus)
        self.assertEqual(request.amount, 190.0)

    async def test_fully_funded_finalizer_crash_returns_balance(self) -> None:
        session = AsyncMock(spec=AsyncSession)
        payment = SimpleNamespace(payment_id=17)
        context = WebAppPaymentContext(
            request=object(),
            session=session,
            user_id=42,
            method="card",
            months=1,
            price=0,
            stars_price=None,
            description="Subscription",
            sale_mode="subscription@basic",
        )
        allocation = PartnerCheckoutBalanceAllocation(7, "RUB", 2, 19000, 19000)
        update_status = AsyncMock(return_value=payment)

        with (
            patch.object(
                billing_partner_checkout,
                "create_webapp_payment_record",
                AsyncMock(return_value=payment),
            ),
            patch.object(
                billing_partner_checkout,
                "get_referral_service",
                return_value=object(),
            ),
            patch.object(billing_partner_checkout, "get_bot", return_value=object()),
            patch.object(billing_partner_checkout, "get_settings", return_value=object()),
            patch.object(billing_partner_checkout, "get_i18n", return_value=object()),
            patch.object(
                billing_partner_checkout,
                "get_subscription_service",
                return_value=object(),
            ),
            patch.object(
                billing_partner_checkout,
                "finalize_successful_payment",
                AsyncMock(side_effect=RuntimeError("crash")),
            ),
            patch.object(
                billing_partner_checkout.payment_dal,
                "update_payment_status_by_db_id",
                update_status,
            ),
        ):
            response = await billing_partner_checkout.create_fully_partner_funded_payment(
                request=cast(web.Request, context.request),
                payment_context=context,
                allocation=allocation,
            )

        self.assertEqual(response.status, 409)
        update_status.assert_awaited_once_with(session, 17, "activation_failed")
        session.rollback.assert_awaited_once()
        session.commit.assert_awaited_once()
