import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from aiohttp import web

from bot.app.web.webapp import billing_payments, billing_quotes, billing_tariff_access
from bot.app.web.webapp.billing_checkout_bundle import build_checkout_bundle
from bot.app.web.webapp.billing_quotes import BasePaymentQuote
from bot.app.web.webapp.payloads import WebAppPaymentCreatePayload
from config.tariffs_config import TariffsConfig
from tests.support.settings_stub import settings_stub

ACCESS_CODE = "ab" * 16


def _settings(with_addons: bool = False) -> SimpleNamespace:
    hidden = {
        "key": "hidden",
        "enabled": False,
        "access_code": ACCESS_CODE,
        "billing_model": "period",
        "monthly_gb": 100 if with_addons else 0,
        "hwid_device_limit": 5 if with_addons else 0,
        "enabled_periods": [12],
        "prices_rub": {"12": 1},
        "prices_stars": {"12": 12},
        "checkout_addons": {
            "devices": {
                "enabled": with_addons,
                "max_extra_devices": 1,
                "price_per_device": 2,
                "stars_price_per_device": 1,
            }
        },
    }
    config = TariffsConfig.model_validate(
        {
            "default_tariff": "standard",
            "tariffs": [
                {
                    "key": "standard",
                    "billing_model": "period",
                    "monthly_gb": 100,
                    "enabled_periods": [12],
                    "prices_rub": {"12": 100},
                },
                hidden,
            ],
        }
    )
    return settings_stub(
        tariffs_config=config,
        DEFAULT_PAYMENT_CURRENCY="RUB",
        USER_HWID_DEVICE_LIMIT=5,
        MY_DEVICES_SECTION_ENABLED=True,
        TRIAL_DAYS_STRATEGY="add_remaining",
        traffic_sale_mode=False,
    )


def _trial(tariff_key: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        subscription_id=7,
        tariff_key=tariff_key,
        provider="trial",
        end_date=datetime.now(UTC) + timedelta(days=3),
    )


def _payload(with_addons: bool = False, method: str = "yookassa") -> WebAppPaymentCreatePayload:
    return WebAppPaymentCreatePayload.model_validate(
        {
            "method": method,
            "months": 12,
            "tariff_key": "hidden",
            "sale_mode": "subscription",
            "checkout_addons": {"device_count": 1 if with_addons else 0},
        }
    )


class HiddenTariffCheckoutTests(IsolatedAsyncioTestCase):
    async def test_private_link_quotes_trial_and_first_purchase(self) -> None:
        for active in (None, _trial(None), _trial("standard")):
            for with_addons, method in ((False, "yookassa"), (True, "yookassa"), (True, "stars")):
                with self.subTest(active=active, with_addons=with_addons, method=method):
                    with (
                        patch.object(
                            billing_quotes, "_get_cached_webapp_settings", return_value={}
                        ),
                        patch.object(
                            billing_quotes.subscription_dal,
                            "get_active_subscription_by_user_id",
                            AsyncMock(return_value=active),
                        ),
                    ):
                        quote, error = await billing_quotes._resolve_base_payment_quote(
                            request=SimpleNamespace(headers={"X-Tariff-Access-Code": ACCESS_CODE}),
                            session=AsyncMock(),
                            user_id=42,
                            db_user=SimpleNamespace(panel_user_uuid=None),
                            payment_payload=_payload(with_addons, method),
                            method=method,
                            settings=_settings(with_addons),
                            subscription_service=AsyncMock(),
                        )

                    self.assertIsNone(error)
                    assert quote is not None
                    self.assertEqual(quote.price, 25 if with_addons else 1)
                    self.assertEqual(quote.stars_price, 24 if method == "stars" else 12)
                    self.assertEqual(quote.period_start, active.end_date if active else None)
                    if with_addons:
                        assert quote.checkout_bundle_snapshot is not None
                        snapshot = json.loads(quote.checkout_bundle_snapshot)
                        self.assertEqual(snapshot["tariff_key"], "hidden")
                        self.assertEqual(snapshot["items"][0]["total_units"], 6)
                        self.assertNotIn(ACCESS_CODE, quote.checkout_bundle_snapshot)
                    else:
                        self.assertIsNone(quote.checkout_bundle_snapshot)

    async def test_private_link_creates_trial_and_first_purchase_payments(self) -> None:
        for active in (None, _trial(None), _trial("standard")):
            for with_addons, method in ((False, "yookassa"), (True, "yookassa"), (True, "stars")):
                with self.subTest(active=active, with_addons=with_addons, method=method):
                    session = AsyncMock()
                    session_context = AsyncMock()
                    session_context.__aenter__.return_value = session
                    create_payment = AsyncMock(return_value=web.json_response({"ok": True}))
                    with (
                        patch.object(billing_payments, "_require_user_id", return_value=42),
                        patch.object(
                            billing_payments,
                            "_enforce_webapp_rate_limit",
                            AsyncMock(return_value=None),
                        ),
                        patch.object(
                            billing_payments,
                            "_parse_model_payload",
                            AsyncMock(return_value=_payload(with_addons, method)),
                        ),
                        patch.object(
                            billing_payments, "get_settings", return_value=_settings(with_addons)
                        ),
                        patch.object(
                            billing_payments, "get_subscription_service", return_value=AsyncMock()
                        ),
                        patch.object(
                            billing_payments, "_get_cached_webapp_settings", return_value={}
                        ),
                        patch.object(
                            billing_payments,
                            "get_session_factory",
                            return_value=lambda context=session_context: context,
                        ),
                        patch.object(
                            billing_payments.user_dal,
                            "get_user_by_id",
                            AsyncMock(
                                return_value=SimpleNamespace(
                                    is_banned=False, language_code="en", panel_user_uuid=None
                                )
                            ),
                        ),
                        patch.object(
                            billing_quotes.subscription_dal,
                            "get_active_subscription_by_user_id",
                            AsyncMock(return_value=active),
                        ),
                        patch("bot.services.account_roles.is_admin", AsyncMock(return_value=False)),
                        patch.object(
                            billing_payments, "_create_subscription_payment", create_payment
                        ),
                    ):
                        response = await billing_payments.create_payment_route(
                            SimpleNamespace(app={}, headers={"X-Tariff-Access-Code": ACCESS_CODE})
                        )

                    self.assertEqual(response.status, 200)
                    create_payment.assert_awaited_once()
                    assert create_payment.await_args is not None
                    kwargs = create_payment.await_args.kwargs
                    self.assertEqual(kwargs["price"], 25 if with_addons else 1)
                    self.assertEqual(kwargs["stars_price"], 24 if method == "stars" else 12)
                    self.assertEqual(kwargs["sale_mode"], "subscription@hidden")
                    self.assertEqual(bool(kwargs["checkout_bundle_snapshot"]), with_addons)

    async def test_private_link_quote_rejects_missing_or_wrong_tariff_code(self) -> None:
        for code in (None, "cd" * 16):
            with self.subTest(code=code):
                with (
                    patch.object(billing_quotes, "_get_cached_webapp_settings", return_value={}),
                    patch.object(
                        billing_tariff_access.subscription_dal,
                        "get_active_subscription_by_user_id",
                        AsyncMock(return_value=_trial("standard")),
                    ),
                ):
                    quote, error = await billing_quotes._resolve_base_payment_quote(
                        request=SimpleNamespace(
                            headers={"X-Tariff-Access-Code": code} if code else {}
                        ),
                        session=AsyncMock(),
                        user_id=42,
                        db_user=SimpleNamespace(panel_user_uuid=None),
                        payment_payload=_payload(),
                        method="yookassa",
                        settings=_settings(),
                        subscription_service=AsyncMock(),
                    )

                self.assertIsNone(quote)
                assert error is not None
                self.assertEqual(error.status, 400)

    def test_bundle_still_rejects_unassigned_hidden_tariff_without_code(self) -> None:
        with self.assertRaises(KeyError):
            build_checkout_bundle(
                BasePaymentQuote(12, 1, 12, "subscription@hidden", None, "RUB"),
                settings=_settings(),
                payment_payload=_payload(),
                method="yookassa",
            )
