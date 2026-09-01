from types import SimpleNamespace
from typing import cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from bot.services.user_balance_service import (
    UserBalanceAllocation,
    UserBalanceError,
    UserBalanceService,
)
from config.settings import Settings


def _settings(*, enabled: bool = True) -> Settings:
    return cast(
        Settings,
        SimpleNamespace(
            balance_settings=SimpleNamespace(
                enabled=enabled,
                currency="RUB",
                topup_min_amount=100,
                topup_max_amount=100_000,
                topup_presets=[300, 500, 1_000],
            ),
            partner_settings=SimpleNamespace(
                enabled=True,
                balance_payment_enabled=True,
            ),
        ),
    )


class UserBalanceQuoteTests(IsolatedAsyncioTestCase):
    async def test_quote_preserves_provider_minimum_for_partial_payment(self) -> None:
        service = UserBalanceService(_settings())
        session = cast(AsyncSession, object())
        with (
            patch(
                "bot.services.user_balance_service.user_dal.lock_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.balance_minor",
                AsyncMock(return_value=18_000),
            ),
        ):
            allocation = await service.quote(
                session,
                user_id=42,
                currency="RUB",
                checkout_total=190,
                minimum_external_amount=50,
            )

        self.assertEqual(allocation.applied_minor, 14_000)
        self.assertEqual(allocation.external_minor, 5_000)

    async def test_quote_rejects_disabled_and_mismatched_currency(self) -> None:
        with self.assertRaisesRegex(UserBalanceError, "user_balance_disabled"):
            await UserBalanceService(_settings(enabled=False)).quote(
                cast(AsyncSession, object()),
                user_id=42,
                currency="RUB",
                checkout_total=190,
            )
        with self.assertRaisesRegex(UserBalanceError, "user_balance_currency_mismatch"):
            await UserBalanceService(_settings()).quote(
                cast(AsyncSession, object()),
                user_id=42,
                currency="USD",
                checkout_total=190,
            )


class UserBalanceLifecycleTests(IsolatedAsyncioTestCase):
    async def test_reservation_is_idempotent_and_validates_payload(self) -> None:
        allocation = UserBalanceAllocation(42, "RUB", 2, 19_000, 14_000)
        existing = SimpleNamespace(user_id=42, currency="RUB", amount_minor=-14_000)
        lookup = AsyncMock(return_value=existing)
        with patch(
            "bot.services.user_balance_service.user_balance_dal.get_ledger_entry_by_key",
            lookup,
        ):
            result = await UserBalanceService.reserve(
                cast(AsyncSession, object()), payment_id=17, allocation=allocation
            )
        self.assertIs(result, existing)

        conflicting = SimpleNamespace(user_id=42, currency="RUB", amount_minor=-13_000)
        with (
            patch(
                "bot.services.user_balance_service.user_balance_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=conflicting),
            ),
            self.assertRaisesRegex(UserBalanceError, "user_balance_reservation_conflict"),
        ):
            await UserBalanceService.reserve(
                cast(AsyncSession, object()), payment_id=17, allocation=allocation
            )

    async def test_payment_topup_webhook_is_idempotent(self) -> None:
        service = UserBalanceService(_settings())
        existing = SimpleNamespace(
            entry_id=7,
            user_id=42,
            currency="RUB",
            amount_minor=50_000,
            kind="payment_topup",
        )
        create = AsyncMock()
        with (
            patch(
                "bot.services.user_balance_service.user_dal.lock_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=existing),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.create_ledger_entry",
                create,
            ),
        ):
            result = await service.credit_payment_topup(
                cast(AsyncSession, object()),
                payment_id=99,
                user_id=42,
                amount=500,
                currency="RUB",
            )
        self.assertIs(result, existing)
        create.assert_not_awaited()

    async def test_payment_topup_keeps_invoice_currency_after_settings_change(self) -> None:
        service = UserBalanceService(_settings())
        created = SimpleNamespace(entry_id=8)
        create = AsyncMock(return_value=created)
        with (
            patch(
                "bot.services.user_balance_service.user_dal.lock_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.create_ledger_entry",
                create,
            ),
        ):
            result = await service.credit_payment_topup(
                cast(AsyncSession, object()),
                payment_id=100,
                user_id=42,
                amount=12.34,
                currency="USD",
            )

        self.assertIs(result, created)
        create_call = create.await_args
        self.assertIsNotNone(create_call)
        assert create_call is not None
        self.assertEqual(create_call.kwargs["currency"], "USD")
        self.assertEqual(create_call.kwargs["currency_scale"], 2)
        self.assertEqual(create_call.kwargs["amount_minor"], 1_234)

    async def test_admin_adjustment_cannot_make_balance_negative(self) -> None:
        service = UserBalanceService(_settings())
        with (
            patch(
                "bot.services.user_balance_service.user_dal.lock_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.balance_minor",
                AsyncMock(return_value=1_000),
            ),
            self.assertRaisesRegex(UserBalanceError, "insufficient_user_balance"),
        ):
            await service.admin_adjust(
                cast(AsyncSession, object()),
                user_id=42,
                actor_admin_id=1,
                mode="subtract",
                amount=20,
                reason="test",
                idempotency_key="adjust:1",
            )

    async def test_conversion_spends_nonwithdrawable_partner_funds_first(self) -> None:
        service = UserBalanceService(_settings())
        user_entry = SimpleNamespace(entry_id=31)
        partner_entry = SimpleNamespace(entry_id=32)
        create_user = AsyncMock(return_value=user_entry)
        create_partner = AsyncMock(return_value=partner_entry)
        with (
            patch(
                "bot.services.user_balance_service.user_dal.lock_user_by_id",
                AsyncMock(return_value=SimpleNamespace(is_banned=False)),
            ),
            patch(
                "bot.services.user_balance_service.partner_dal.get_profile_by_user_id",
                AsyncMock(return_value=SimpleNamespace(partner_id=7, status="active")),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.user_balance_service.partner_dal.get_ledger_entry_by_key",
                AsyncMock(return_value=None),
            ),
            patch(
                "bot.services.user_balance_service.partner_dal.balance_minor",
                AsyncMock(return_value=30_000),
            ),
            patch(
                "bot.services.user_balance_service.partner_dal.withdrawable_balance_minor",
                AsyncMock(return_value=20_000),
            ),
            patch(
                "bot.services.user_balance_service.user_balance_dal.create_ledger_entry",
                create_user,
            ),
            patch(
                "bot.services.user_balance_service.partner_dal.create_ledger_entry",
                create_partner,
            ),
        ):
            result = await service.convert(
                cast(AsyncSession, object()),
                user_id=42,
                actor_admin_id=1,
                direction="partner_to_user",
                amount=150,
                reason="return converted funds",
                idempotency_key="convert:1",
            )

        self.assertEqual(result, (user_entry, partner_entry))
        partner_call = create_partner.await_args
        self.assertIsNotNone(partner_call)
        assert partner_call is not None
        self.assertEqual(partner_call.kwargs["amount_minor"], -15_000)
        self.assertEqual(partner_call.kwargs["withdrawable_amount_minor"], -5_000)
