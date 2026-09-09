from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from bot.app.web.webapp.serializers import (
    _refresh_pending_promo_payment,
    _serialize_pending_promo_payment,
    _suggested_checkout_promo,
)
from db.dal import payment_checkout_dal, payment_dal


class PendingPromoPaymentTests(IsolatedAsyncioTestCase):
    @staticmethod
    def _payment(payment_id: int, *, status: str = "pending_wata") -> SimpleNamespace:
        return SimpleNamespace(
            payment_id=payment_id,
            provider_payment_url=f"https://pay.example/{payment_id}",
            provider="wata",
            status=status,
            amount=495.0,
            checkout_base_amount=550.0,
            checkout_discount_amount=55.0,
            currency="RUB",
            promo_discount_percent=10,
            subscription_duration_months=1,
            purchased_gb=None,
            purchased_hwid_devices=None,
            sale_mode="subscription@standard",
            tariff_key="standard",
            promo_effect_summary="-10%",
            promo_code_used=SimpleNamespace(code="PERSONAL10", archived_code=None),
            created_at=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )

    @patch(
        "bot.app.web.webapp.serializers.resolve_promo_checkout_suggestion",
        new_callable=AsyncMock,
    )
    async def test_pending_payment_takes_priority_over_new_suggestion(
        self,
        resolve_suggestion: AsyncMock,
    ) -> None:
        result = await _suggested_checkout_promo(
            cast(AsyncSession, object()),
            user_id=42,
            pending_payment={"payment_id": 17},
        )

        self.assertIsNone(result)
        resolve_suggestion.assert_not_awaited()

    @patch(
        "bot.app.web.webapp.serializers.resolve_promo_checkout_suggestion",
        new_callable=AsyncMock,
    )
    async def test_suggestion_is_resolved_without_pending_payment(
        self,
        resolve_suggestion: AsyncMock,
    ) -> None:
        resolve_suggestion.return_value = "PERSONAL20"

        result = await _suggested_checkout_promo(
            cast(AsyncSession, object()),
            user_id=42,
            pending_payment=None,
        )

        self.assertEqual(result, "PERSONAL20")
        await_args = resolve_suggestion.await_args
        assert await_args is not None
        self.assertEqual(await_args.args[0].user_id, 42)

    async def test_lookup_requires_owned_promo_and_reusable_pending_url(self) -> None:
        payment = SimpleNamespace(payment_id=17)
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: payment))
        )

        result = await payment_dal.get_latest_resumable_promo_payment(
            session,
            user_id=42,
        )

        self.assertIs(result, payment)
        statement = session.execute.await_args.args[0]
        rendered = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("payments.user_id = 42", rendered)
        self.assertIn("payments.promo_code_id IS NOT NULL", rendered)
        self.assertIn("payments.partner_balance_amount_minor > 0", rendered)
        self.assertIn("payments.provider_payment_url IS NOT NULL", rendered)
        self.assertIn("lower(trim(payments.status)) LIKE 'pending_%%'", rendered)
        self.assertIn("ORDER BY payments.created_at DESC, payments.payment_id DESC", rendered)

    async def test_checkout_reuse_matches_requested_promo_and_partner_balance(self) -> None:
        session = SimpleNamespace(
            execute=AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
        )

        await payment_checkout_dal.find_recent_pending_provider_payment_for_checkout(
            cast(AsyncSession, session),
            user_id=42,
            provider="pally",
            pending_status="pending_pally",
            currency="RUB",
            sale_mode="subscription@standard",
            months=1,
            purchased_gb=None,
            purchased_hwid_devices=None,
            match_reservations=True,
            requested_promo_code="save20",
            requested_partner_balance=True,
        )

        statement = session.execute.await_args.args[0]
        rendered = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("upper(coalesce(nullif(trim(promo_codes.archived_code)", rendered.lower())
        self.assertIn("= 'SAVE20'", rendered)
        self.assertIn("coalesce(payments.partner_balance_amount_minor, 0) > 0", rendered)

    async def test_superseded_checkout_scope_ignores_amount_and_bundle_selection(self) -> None:
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=SimpleNamespace(
                    scalars=lambda: SimpleNamespace(all=list),
                )
            )
        )
        payment = SimpleNamespace(
            payment_id=18,
            user_id=42,
            provider="pally",
            currency="RUB",
            sale_mode="subscription@standard",
            tariff_key="standard",
            subscription_duration_months=1,
            purchased_gb=None,
            purchased_hwid_devices=None,
            hwid_traffic_bonus_bytes=None,
            tariff_change_quote_snapshot=None,
            entitlement_context_snapshot="active-subscription-v1",
            checkout_bundle_hash="new-device-selection",
            amount=495.0,
        )

        await payment_checkout_dal.list_earlier_pending_provider_payments_for_checkout_scope(
            cast(AsyncSession, session),
            payment,
            pending_status="pending_pally",
        )

        statement = session.execute.await_args.args[0]
        rendered = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )
        self.assertIn("payments.payment_id < 18", rendered)
        self.assertIn("payments.entitlement_context_snapshot = 'active-subscription-v1'", rendered)
        where_clause = rendered.split("WHERE", 1)[1]
        self.assertNotIn("checkout_bundle_hash", where_clause)
        self.assertNotIn("payments.amount", where_clause)

    @patch(
        "bot.app.web.webapp.serializers.refresh_payment_status_for_request",
        new_callable=AsyncMock,
    )
    @patch.object(payment_dal, "get_latest_resumable_promo_payment", new_callable=AsyncMock)
    async def test_refresh_discards_expired_payment_before_showing_next_live_link(
        self,
        get_latest: AsyncMock,
        refresh_status: AsyncMock,
    ) -> None:
        expired = self._payment(18)
        live = self._payment(17)
        get_latest.side_effect = [expired, live, live, live]

        result = await _refresh_pending_promo_payment(
            cast(Any, SimpleNamespace()),
            cast(AsyncSession, object()),
            user_id=42,
        )

        self.assertEqual(result["payment_id"], 17)
        self.assertEqual(refresh_status.await_count, 2)
        self.assertIs(refresh_status.await_args_list[0].args[2], expired)
        self.assertIs(refresh_status.await_args_list[1].args[2], live)

    @patch(
        "bot.app.web.webapp.serializers.refresh_payment_status_for_request",
        new_callable=AsyncMock,
    )
    @patch.object(payment_dal, "get_latest_resumable_promo_payment", new_callable=AsyncMock)
    async def test_refresh_returns_no_banner_after_last_link_expires(
        self,
        get_latest: AsyncMock,
        refresh_status: AsyncMock,
    ) -> None:
        expired = self._payment(18)
        get_latest.side_effect = [expired, None]

        result = await _refresh_pending_promo_payment(
            cast(Any, SimpleNamespace()),
            cast(AsyncSession, object()),
            user_id=42,
        )

        self.assertIsNone(result)
        refresh_status.assert_awaited_once()

    def test_serializer_preserves_discounted_checkout_details(self) -> None:
        payment = SimpleNamespace(
            payment_id=17,
            provider_payment_url="https://pay.example/17",
            provider="yookassa",
            status="pending_yookassa",
            amount=720.0,
            checkout_base_amount=900.0,
            checkout_discount_amount=180.0,
            currency="RUB",
            promo_discount_percent=20,
            subscription_duration_months=3,
            purchased_gb=None,
            purchased_hwid_devices=None,
            sale_mode="subscription@pro",
            tariff_key="pro",
            promo_effect_summary="-20%",
            promo_code_used=SimpleNamespace(code="SAVE20", archived_code=None),
            created_at=datetime(2026, 7, 29, 12, 30, tzinfo=UTC),
        )

        self.assertEqual(
            _serialize_pending_promo_payment(payment),
            {
                "payment_id": 17,
                "payment_url": "https://pay.example/17",
                "provider": "yookassa",
                "status": "pending_yookassa",
                "amount": 720.0,
                "base_amount": 900.0,
                "currency": "RUB",
                "discount_amount": 180.0,
                "discount_percent": 20.0,
                "partner_balance_amount": 0.0,
                "partner_balance_amount_minor": 0,
                "partner_balance_currency_scale": 0,
                "months": 3,
                "duration_days": None,
                "period_semantics": None,
                "purchased_gb": None,
                "purchased_hwid_devices": None,
                "sale_mode": "subscription@pro",
                "tariff_key": "pro",
                "promo_code": "SAVE20",
                "promo_effect_summary": "-20%",
                "checkout_addons": [],
                "checkout_addons_amount": 0.0,
                "created_at": "2026-07-29T12:30:00+00:00",
            },
        )

    def test_serializer_includes_partner_balance_as_checkout_discount(self) -> None:
        payment = self._payment(19)
        payment.amount = 300.0
        payment.checkout_base_amount = 550.0
        payment.checkout_discount_amount = 50.0
        payment.partner_balance_amount_minor = 20000
        payment.partner_balance_currency_scale = 2

        result = _serialize_pending_promo_payment(payment)

        assert result is not None
        self.assertEqual(result["base_amount"], 550.0)
        self.assertEqual(result["amount"], 300.0)
        self.assertEqual(result["discount_amount"], 250.0)
        self.assertEqual(result["partner_balance_amount"], 200.0)
        self.assertEqual(result["partner_balance_amount_minor"], 20000)
