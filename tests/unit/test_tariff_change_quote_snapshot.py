from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.webapp import billing_options
from bot.services.subscription_service_impl.tariff_change_quote import (
    TariffChangePreflightResult,
    TariffChangePreflightStatus,
    build_tariff_change_quote_snapshot,
    parse_tariff_change_quote_snapshot,
    preflight_paid_tariff_change,
)


class _SessionContext:
    async def __aenter__(self) -> AsyncMock:
        self.session = AsyncMock()
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


def _quoted_payment(**overrides: object) -> Any:
    values: dict[str, object] = {
        "user_id": 42,
        "amount": 75.5,
        "currency": "RUB",
        "sale_mode": "tariff_upgrade@pro",
        "tariff_key": "pro",
        "tariff_change_quote_snapshot": build_tariff_change_quote_snapshot(
            source_tariff_key="basic",
            target_tariff_key="pro",
            required_amount=75.5,
            currency="RUB",
            convertible_hwid_purchase_ids=[],
        ),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _active_subscription(**overrides: object) -> Any:
    values: dict[str, object] = {
        "user_id": 42,
        "tariff_key": "basic",
        "provider": "yookassa",
        "auto_renew_enabled": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _preflight(
    payment: Any,
    active_subscription: Any,
    *,
    configured_tariffs: tuple[str, ...] = ("basic", "pro"),
) -> TariffChangePreflightResult:
    tariffs = {key: SimpleNamespace(key=key, billing_model="period") for key in configured_tariffs}
    config: Any = SimpleNamespace(
        require=lambda key: tariffs[key],
        require_configured=lambda key: tariffs[key],
    )
    return preflight_paid_tariff_change(
        payment=payment,
        active_subscription=active_subscription,
        tariffs_config=config,
        expected_user_id=42,
        expected_target_tariff_key="pro",
    )


class TariffChangeQuoteSnapshotTests(IsolatedAsyncioTestCase):
    async def test_payment_route_persists_exact_source_amount_and_hwid_quote(self) -> None:
        tariffs = {
            "legacy-basic": SimpleNamespace(key="basic"),
            "pro": SimpleNamespace(key="pro"),
        }
        config = SimpleNamespace(
            require=lambda key: tariffs[key],
            require_configured=lambda key: tariffs[key],
        )
        settings = SimpleNamespace(
            tariffs_config=config,
            DEFAULT_LANGUAGE="en",
        )
        subscription = SimpleNamespace(
            tariff_key="legacy-basic",
            tribute_subscription_id=None,
        )
        payment_response = web.json_response({"ok": True})
        create_payment = AsyncMock(return_value=payment_response)

        with (
            patch.object(billing_options, "_require_user_id", return_value=42),
            patch.object(
                billing_options,
                "_parse_model_payload",
                AsyncMock(return_value=SimpleNamespace(method="yookassa", tariff_key="pro")),
            ),
            patch.object(billing_options, "get_settings", return_value=settings),
            patch.object(
                billing_options,
                "default_payment_currency_code_for_settings",
                return_value="RUB",
            ),
            patch.object(
                billing_options,
                "get_session_factory",
                return_value=lambda: _SessionContext(),
            ),
            patch.object(
                billing_options,
                "get_subscription_service",
                return_value=SimpleNamespace(
                    calculate_tariff_switch_options_with_hwid=AsyncMock(
                        return_value={
                            "mode": "period_to_period",
                            "paid_diff_rub": 75.5,
                            "convertible_hwid_purchase_ids": [7, 9],
                        }
                    )
                ),
            ),
            patch.object(
                billing_options.user_dal,
                "get_user_by_id",
                AsyncMock(
                    return_value=SimpleNamespace(
                        is_banned=False,
                        panel_user_uuid="panel-user",
                        language_code="en",
                    )
                ),
            ),
            patch.object(
                billing_options.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=subscription),
            ),
            patch.object(billing_options, "_active_tribute_recurrence", return_value=False),
            patch.object(billing_options, "_create_subscription_payment", create_payment),
        ):
            response = await billing_options.tariff_change_payment_route(SimpleNamespace())

        self.assertIs(response, payment_response)
        create_args = create_payment.await_args
        assert create_args is not None
        raw_snapshot = create_args.kwargs["tariff_change_quote_snapshot"]
        snapshot = parse_tariff_change_quote_snapshot(raw_snapshot)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot.source_tariff_key, "basic")
        self.assertEqual(snapshot.target_tariff_key, "pro")
        self.assertEqual(snapshot.required_amount, Decimal("75.5"))
        self.assertEqual(snapshot.currency, "RUB")
        self.assertEqual(snapshot.convertible_hwid_purchase_ids, (7, 9))

    def test_snapshot_amount_comparison_uses_currency_precision(self) -> None:
        raw_snapshot = build_tariff_change_quote_snapshot(
            source_tariff_key="basic",
            target_tariff_key="pro",
            required_amount=75.5,
            currency="rub",
            convertible_hwid_purchase_ids=[],
        )
        snapshot = parse_tariff_change_quote_snapshot(raw_snapshot)

        assert snapshot is not None
        self.assertTrue(snapshot.charged_amount_matches(75.5000001))
        self.assertFalse(snapshot.charged_amount_matches(75.49))

    def test_preflight_rejects_cross_payment_identity_amount_and_currency(self) -> None:
        invalid_payments = (
            _quoted_payment(user_id=777),
            _quoted_payment(amount=75.49),
            _quoted_payment(currency="USD"),
            _quoted_payment(sale_mode="tariff_upgrade@other"),
            _quoted_payment(tariff_key="other"),
        )

        for payment in invalid_payments:
            with self.subTest(payment=payment):
                result = _preflight(payment, _active_subscription())
                self.assertEqual(result.status, TariffChangePreflightStatus.INVALID)

    def test_preflight_classifies_only_deterministic_state_drift_as_stale(self) -> None:
        cases = (
            (
                _active_subscription(tariff_key="pro"),
                ("basic", "pro"),
                "source_tariff_changed",
            ),
            (
                _active_subscription(),
                ("basic",),
                "target_tariff_unconfigured",
            ),
            (
                _active_subscription(provider="tribute", auto_renew_enabled=True),
                ("basic", "pro"),
                "active_tribute_recurrence",
            ),
        )

        for active_subscription, configured_tariffs, reason in cases:
            with self.subTest(reason=reason):
                result = _preflight(
                    _quoted_payment(),
                    active_subscription,
                    configured_tariffs=configured_tariffs,
                )
                self.assertEqual(
                    result.status,
                    TariffChangePreflightStatus.DETERMINISTIC_STALE,
                )
                self.assertEqual(result.reason, reason)

    def test_preflight_accepts_matching_immutable_quote(self) -> None:
        result = _preflight(_quoted_payment(), _active_subscription())

        self.assertEqual(result.status, TariffChangePreflightStatus.OK)
        self.assertTrue(result.allowed)

    def test_preflight_rejects_billing_model_drift_under_the_same_keys(self) -> None:
        tariffs = {
            "basic": SimpleNamespace(key="basic", billing_model="period"),
            "pro": SimpleNamespace(key="pro", billing_model="traffic"),
        }
        config: Any = SimpleNamespace(require=lambda key: tariffs[key])

        result = preflight_paid_tariff_change(
            payment=_quoted_payment(),
            active_subscription=_active_subscription(),
            tariffs_config=config,
            expected_user_id=42,
            expected_target_tariff_key="pro",
        )

        self.assertEqual(
            result.status,
            TariffChangePreflightStatus.DETERMINISTIC_STALE,
        )
        self.assertEqual(result.reason, "target_tariff_changed")
