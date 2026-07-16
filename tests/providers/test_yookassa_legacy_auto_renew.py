from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from bot.payment_providers.yookassa import legacy_auto_renew, success
from db.dal import payment_dal


class _I18n:
    def gettext(self, _lang, key, **_kwargs):
        return key


def _subscription(**overrides):
    values = {
        "subscription_id": 555,
        "user_id": 42,
        "provider": "yookassa",
        "duration_months": 1,
        "tariff_key": "standard",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _quote(**overrides):
    values = {
        "amount": 399.0,
        "currency": "RUB",
        "months": 1,
        "sale_mode": "subscription@standard",
        "tariff_key": "standard",
        "hwid_quote": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _metadata(**overrides):
    values = {
        "user_id": "42",
        "subscription_months": "1",
        "auto_renew_for_subscription_id": "555",
        "sale_mode": "subscription@standard",
    }
    values.update(overrides)
    return values


class LegacyAutoRenewOrderTests(IsolatedAsyncioTestCase):
    async def _ensure_order(
        self,
        *,
        sub=None,
        quote=None,
        metadata=None,
        user_id=42,
    ):
        session = AsyncMock()
        session.get.return_value = sub or _subscription()
        subscription_service = SimpleNamespace(
            quote_subscription_renewal=AsyncMock(return_value=quote or _quote())
        )
        return await legacy_auto_renew.ensure_legacy_auto_renew_payment(
            session,
            provider_payment_id="yk-legacy-1",
            user_id=user_id,
            subscription_id=555,
            metadata=metadata or _metadata(),
            description="Renewal",
            subscription_service=subscription_service,
        )

    async def test_rejects_subscription_owned_by_another_user(self):
        with self.assertRaisesRegex(ValueError, "another user"):
            await self._ensure_order(sub=_subscription(user_id=99))

    async def test_rejects_duration_mismatch(self):
        with self.assertRaisesRegex(ValueError, "duration"):
            await self._ensure_order(metadata=_metadata(subscription_months="3"))

    async def test_rejects_tariff_mismatch(self):
        with self.assertRaisesRegex(ValueError, "tariff"):
            await self._ensure_order(metadata=_metadata(sale_mode="subscription@premium"))

    async def test_rejects_non_yookassa_subscription(self):
        with self.assertRaisesRegex(ValueError, "another provider"):
            await self._ensure_order(sub=_subscription(provider="cloudpayments"))

    async def test_rejects_unverifiable_hwid_metadata(self):
        with self.assertRaisesRegex(ValueError, "no authoritative quote"):
            await self._ensure_order(metadata=_metadata(hwid_devices="2"))

    async def test_accepts_hwid_metadata_only_when_it_matches_authoritative_quote(self):
        valid_from = datetime(2099, 2, 1, tzinfo=UTC)
        valid_until = datetime(2099, 3, 1, tzinfo=UTC)
        hwid_quote = {
            "device_count": 2,
            "price": 50.0,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "pricing_period_months": 1,
            "proration_ratio": 1.0,
            "full_price": 50.0,
        }
        payment = SimpleNamespace(payment_id=7)
        ensure_order = AsyncMock(return_value=payment)
        with patch.object(
            legacy_auto_renew.payment_dal,
            "ensure_payment_with_provider_id",
            ensure_order,
        ):
            result = await self._ensure_order(
                quote=_quote(amount=449.0, hwid_quote=hwid_quote),
                metadata=_metadata(
                    hwid_devices="2",
                    hwid_valid_from=valid_from.isoformat(),
                    hwid_valid_until=valid_until.isoformat(),
                    hwid_pricing_period_months="1",
                    hwid_proration_ratio="1.0",
                    hwid_full_price="50.0",
                ),
            )

        assert result is payment
        assert ensure_order.await_args.kwargs["amount"] == 449.0
        assert ensure_order.await_args.kwargs["purchased_hwid_devices"] == 2
        assert ensure_order.await_args.kwargs["hwid_valid_until"] == valid_until

    async def test_rejects_existing_provider_id_bound_to_another_order(self):
        existing = SimpleNamespace(
            payment_id=7,
            user_id=99,
            amount=399.0,
            currency="RUB",
            subscription_duration_months=1,
            provider="yookassa",
            sale_mode="subscription@standard",
            tariff_key="standard",
            purchased_gb=None,
            purchased_hwid_devices=None,
            hwid_valid_from=None,
            hwid_valid_until=None,
            hwid_pricing_period_months=None,
            hwid_proration_ratio=None,
            hwid_full_price=None,
        )
        with (
            patch.object(
                payment_dal,
                "get_payment_by_provider_payment_id",
                AsyncMock(return_value=existing),
            ),
            self.assertRaisesRegex(ValueError, "different order"),
        ):
            await payment_dal.ensure_payment_with_provider_id(
                AsyncMock(),
                user_id=42,
                amount=399.0,
                currency="RUB",
                months=1,
                description="Renewal",
                provider="yookassa",
                provider_payment_id="yk-legacy-1",
                sale_mode="subscription@standard",
                tariff_key="standard",
            )

    async def test_concurrent_provider_id_claim_reloads_and_validates_winner(self):
        winner = SimpleNamespace(
            payment_id=7,
            user_id=42,
            amount=399.0,
            currency="RUB",
            subscription_duration_months=1,
            provider="yookassa",
            sale_mode="subscription@standard",
            tariff_key="standard",
            purchased_gb=None,
            purchased_hwid_devices=None,
            hwid_valid_from=None,
            hwid_valid_until=None,
            hwid_pricing_period_months=None,
            hwid_proration_ratio=None,
            hwid_full_price=None,
        )
        insert_result = SimpleNamespace(scalar_one_or_none=lambda: None)
        session = AsyncMock()
        session.execute.return_value = insert_result
        get_payment = AsyncMock(side_effect=[None, winner])
        with (
            patch.object(
                payment_dal,
                "get_payment_by_provider_payment_id",
                get_payment,
            ),
            patch.object(
                payment_dal,
                "_validate_payment_record_references",
                AsyncMock(return_value=None),
            ),
        ):
            payment = await payment_dal.ensure_payment_with_provider_id(
                session,
                user_id=42,
                amount=399.0,
                currency="RUB",
                months=1,
                description="Renewal",
                provider="yookassa",
                provider_payment_id="yk-legacy-1",
                sale_mode="subscription@standard",
                tariff_key="standard",
            )

        assert payment is winner
        assert get_payment.await_count == 2
        assert get_payment.await_args_list[0].kwargs["fresh"] is True
        assert get_payment.await_args_list[1].kwargs["fresh"] is True
        rendered = str(session.execute.await_args.args[0])
        assert "ON CONFLICT (provider, provider_payment_id) DO NOTHING" in rendered


class LegacyAutoRenewFulfillmentTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = AsyncMock()
        self.session.get.return_value = _subscription()
        self.payment = SimpleNamespace(
            payment_id=5,
            status="pending_yookassa",
            tariff_key="standard",
            user_id=42,
            amount=399.0,
            currency="RUB",
            sale_mode="subscription@standard",
            subscription_duration_months=1,
            purchased_hwid_devices=None,
            promo_code_id=None,
        )
        self.updated_payment = SimpleNamespace(
            payment_id=5,
            status="succeeded",
            tariff_key="standard",
        )
        self.db_user = SimpleNamespace(
            user_id=42,
            username="alice",
            language_code="en",
            referred_by_id=None,
        )
        self.subscription_service = SimpleNamespace(
            quote_subscription_renewal=AsyncMock(return_value=_quote()),
            activate_subscription=AsyncMock(
                return_value={
                    "subscription_id": 555,
                    "end_date": datetime(2099, 2, 1, tzinfo=UTC),
                    "tariff_key": "standard",
                    "was_extension": True,
                }
            ),
        )
        self.referral_service = SimpleNamespace(
            apply_referral_bonuses_for_payment=AsyncMock(return_value={})
        )
        self.settings = SimpleNamespace(
            traffic_sale_mode=False,
            yookassa_autopayments_active=False,
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            LKNPD_RECEIPT_NAME_TRAFFIC="{gb} GB",
            LKNPD_RECEIPT_NAME_SUBSCRIPTION="{months} months",
        )

    async def _process(self, *, amount="399.00", currency="RUB"):
        payment_info = {
            "id": "yk-legacy-1",
            "status": "succeeded",
            "paid": True,
            "amount": {"value": amount, "currency": currency},
            "metadata": _metadata(),
            "description": "Renewal",
        }
        ensure_order = AsyncMock(return_value=self.payment)
        update_status = AsyncMock(return_value=self.updated_payment)
        with (
            patch.object(
                legacy_auto_renew.payment_dal,
                "ensure_payment_with_provider_id",
                ensure_order,
            ),
            patch.object(
                success.payment_dal,
                "get_payment_by_db_id",
                AsyncMock(return_value=self.payment),
            ),
            patch.object(
                success.payment_dal,
                "claim_payment_finalization",
                AsyncMock(return_value=self.payment),
            ),
            patch.object(
                success.payment_dal,
                "update_payment_status_by_db_id",
                update_status,
            ),
            patch.object(success.user_dal, "lock_user_by_id", AsyncMock(return_value=None)),
            patch.object(
                success.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=self.db_user),
            ),
            patch.object(
                success,
                "prepare_config_links",
                AsyncMock(return_value=("link", "https://example.test/sub")),
            ),
            patch.object(success, "send_success_message_to_user", AsyncMock()),
        ):
            result = await success.process_successful_payment(
                self.session,
                AsyncMock(),
                payment_info,
                _I18n(),
                self.settings,
                AsyncMock(),
                self.subscription_service,
                self.referral_service,
            )
        return result, ensure_order, update_status

    async def test_valid_legacy_callback_uses_authoritative_quote_and_fulfills(self):
        result, ensure_order, update_status = await self._process()

        assert result is not None
        assert result["payment_db_id"] == 5
        assert result["is_auto_renew"] is True
        ensure_kwargs = ensure_order.await_args.kwargs
        assert ensure_kwargs["amount"] == 399.0
        assert ensure_kwargs["currency"] == "RUB"
        assert ensure_kwargs["months"] == 1
        self.subscription_service.activate_subscription.assert_awaited_once()
        assert update_status.await_args.kwargs["new_status"] == "succeeded"

    async def test_underpayment_is_rejected_against_authoritative_quote(self):
        result, ensure_order, update_status = await self._process(amount="1.00")

        assert result is None
        assert ensure_order.await_args.kwargs["amount"] == 399.0
        self.subscription_service.activate_subscription.assert_not_awaited()
        assert update_status.await_args.args[2] == "failed_amount_mismatch"

    async def test_wrong_currency_is_rejected_against_authoritative_quote(self):
        result, ensure_order, update_status = await self._process(currency="USD")

        assert result is None
        assert ensure_order.await_args.kwargs["currency"] == "RUB"
        self.subscription_service.activate_subscription.assert_not_awaited()
        assert update_status.await_args.args[2] == "failed_currency_mismatch"
