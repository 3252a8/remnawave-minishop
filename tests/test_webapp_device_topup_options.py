import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import ANY, AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import billing as billing_module


class _SessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return SimpleNamespace()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class WebAppDeviceTopupOptionsTests(IsolatedAsyncioTestCase):
    async def test_serializes_active_hwid_validity_window(self):
        active_until = datetime(2099, 1, 2, 3, 4, tzinfo=timezone.utc)
        valid_from = datetime(2099, 1, 1, 3, 4, tzinfo=timezone.utc)
        tariff = SimpleNamespace(
            key="standard",
            billing_model="period",
            hwid_device_packages=SimpleNamespace(
                rub=[SimpleNamespace(count=1)],
                stars=[],
            ),
            name=lambda lang: "Standard",
        )
        settings = SimpleNamespace(
            MY_DEVICES_SECTION_ENABLED=True,
            tariffs_config=SimpleNamespace(require=lambda key: tariff),
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(
                return_value={
                    "max_devices": 4,
                    "extra_hwid_devices": 1,
                    "extra_hwid_devices_valid_until": active_until,
                    "device_topup_renewal_available": True,
                }
            ),
            quote_hwid_device_topup=AsyncMock(
                return_value={
                    "price": 50,
                    "valid_from": valid_from,
                    "valid_until": active_until,
                    "proration_ratio": 0.5,
                }
            ),
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(),
                "subscription_service": subscription_service,
            }
        )
        db_user = SimpleNamespace(
            is_banned=False,
            panel_user_uuid="panel-user",
            language_code="en",
        )
        sub = SimpleNamespace(
            tariff_key="standard",
            extra_hwid_devices=1,
        )

        with (
            patch.object(billing_module, "_require_user_id", return_value=42),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
        ):
            response = await billing_module.device_topup_options_route(request)

        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertEqual(payload["extra_hwid_devices_valid_until"], active_until.isoformat())
        self.assertEqual(payload["extra_hwid_devices_valid_until_text"], "02.01.2099 03:04")
        self.assertEqual(payload["plans"][0]["valid_from"], valid_from.isoformat())
        self.assertEqual(payload["plans"][0]["valid_until"], active_until.isoformat())

    async def test_offers_only_immediate_topup_when_existing_extra_expires_early(self):
        current_extra_until = datetime(2099, 1, 16, tzinfo=timezone.utc)
        subscription_until = datetime(2099, 2, 1, tzinfo=timezone.utc)
        tariff = SimpleNamespace(
            key="standard",
            billing_model="period",
            hwid_device_packages=SimpleNamespace(
                rub=[SimpleNamespace(count=1)],
                stars=[],
            ),
            name=lambda lang: "Standard",
        )
        settings = SimpleNamespace(
            MY_DEVICES_SECTION_ENABLED=True,
            tariffs_config=SimpleNamespace(require=lambda key: tariff),
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
        )

        async def quote_hwid_device_topup(*args, **kwargs):
            if kwargs.get("renewal"):
                return {
                    "price": 25,
                    "valid_from": current_extra_until,
                    "valid_until": subscription_until,
                    "proration_ratio": 0.5,
                }
            return {
                "price": 50,
                "valid_from": datetime(2099, 1, 1, tzinfo=timezone.utc),
                "valid_until": subscription_until,
                "proration_ratio": 1.0,
            }

        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(
                return_value={
                    "max_devices": 3,
                    "extra_hwid_devices": 1,
                    "extra_hwid_devices_valid_until": current_extra_until,
                    "extra_hwid_devices_valid_until_text": "16.01.2099 00:00",
                    "device_topup_renewal_available": True,
                }
            ),
            quote_hwid_device_topup=AsyncMock(side_effect=quote_hwid_device_topup),
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(),
                "subscription_service": subscription_service,
            }
        )
        db_user = SimpleNamespace(
            is_banned=False,
            panel_user_uuid="panel-user",
            language_code="en",
        )
        sub = SimpleNamespace(
            tariff_key="standard",
            extra_hwid_devices=1,
        )

        with (
            patch.object(billing_module, "_require_user_id", return_value=42),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
        ):
            response = await billing_module.device_topup_options_route(request)

        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertEqual([plan["sale_mode"] for plan in payload["plans"]], ["hwid_devices"])
        self.assertEqual([plan["price"] for plan in payload["plans"]], [50])
        self.assertFalse(payload["plans"][0]["renewal"])
        self.assertEqual(payload["plans"][0]["valid_until"], subscription_until.isoformat())
        self.assertEqual(payload["renewal_available"], False)
        self.assertEqual(payload["renewal_recommended_count"], 0)
        renewal_flags = [
            call.kwargs.get("renewal")
            for call in subscription_service.quote_hwid_device_topup.await_args_list
        ]
        self.assertEqual(
            renewal_flags,
            [False],
        )

    async def test_create_payment_route_quotes_hwid_with_app_subscription_service(self):
        tariff = SimpleNamespace(
            key="standard",
            billing_model="period",
            enabled_periods=[1],
            hwid_device_packages=SimpleNamespace(
                rub=[SimpleNamespace(count=1)],
                stars=[],
            ),
        )
        settings = SimpleNamespace(
            traffic_sale_mode=False,
            tariffs_config=SimpleNamespace(require=lambda key: tariff),
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            ADMIN_IDS=[],
        )
        quote = {
            "price": 25,
            "valid_from": datetime(2099, 1, 1, tzinfo=timezone.utc),
            "valid_until": datetime(2099, 4, 1, tzinfo=timezone.utc),
            "pricing_period_months": 3,
            "proration_ratio": 1.0,
            "full_price": 25,
        }
        subscription_service = SimpleNamespace(
            quote_hwid_device_topup=AsyncMock(return_value=quote)
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(),
                "subscription_service": subscription_service,
            }
        )
        db_user = SimpleNamespace(
            is_banned=False,
            panel_user_uuid="panel-user",
            language_code="en",
            telegram_id=42,
        )
        sub = SimpleNamespace(tariff_key="standard")

        async def _fake_create_payment(**kwargs):
            return billing_module.web.json_response(
                {
                    "ok": True,
                    "price": kwargs["price"],
                    "hwid_valid_until": kwargs["hwid_quote"]["valid_until"].isoformat(),
                }
            )

        with (
            patch.object(billing_module, "_require_user_id", return_value=42),
            patch.object(
                billing_module,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module,
                "_read_json",
                AsyncMock(
                    return_value={
                        "method": "yookassa",
                        "months": 1,
                        "device_count": 1,
                        "tariff_key": "standard",
                        "sale_mode": "hwid_devices",
                    }
                ),
            ),
            patch.object(
                billing_module,
                "_get_cached_webapp_settings",
                return_value={"subscription_options": {}, "stars_subscription_options": {}},
            ),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
            patch.object(
                billing_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch.object(
                billing_module,
                "_create_subscription_payment",
                AsyncMock(side_effect=_fake_create_payment),
            ) as create_payment,
        ):
            response = await billing_module.create_payment_route(request)

        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["price"], 25)
        subscription_service.quote_hwid_device_topup.assert_awaited_once()
        create_payment.assert_awaited_once()

    async def test_create_payment_route_adds_hwid_renewal_to_subscription_payment(self):
        tariff = SimpleNamespace(
            key="standard",
            billing_model="period",
            enabled_periods=[1],
            hwid_device_packages=SimpleNamespace(
                rub=[SimpleNamespace(count=1)],
                stars=[],
            ),
            period_price=lambda months, currency: 100 if currency == "rub" else None,
        )
        settings = SimpleNamespace(
            traffic_sale_mode=False,
            tariffs_config=SimpleNamespace(require=lambda key: tariff),
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
            ADMIN_IDS=[],
        )
        hwid_quote = {
            "price": 50,
            "device_count": 1,
            "valid_from": datetime(2099, 1, 1, tzinfo=timezone.utc),
            "valid_until": datetime(2099, 2, 1, tzinfo=timezone.utc),
            "pricing_period_months": 1,
            "proration_ratio": 1.0,
            "full_price": 50,
        }
        subscription_service = SimpleNamespace(
            quote_hwid_device_renewal_for_subscription=AsyncMock(return_value=hwid_quote)
        )
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(),
                "subscription_service": subscription_service,
            }
        )
        db_user = SimpleNamespace(
            is_banned=False,
            panel_user_uuid="panel-user",
            language_code="en",
            telegram_id=42,
        )

        async def _fake_create_payment(**kwargs):
            return billing_module.web.json_response(
                {
                    "ok": True,
                    "price": kwargs["price"],
                    "hwid_device_count": kwargs["hwid_quote"]["device_count"],
                }
            )

        with (
            patch.object(billing_module, "_require_user_id", return_value=42),
            patch.object(
                billing_module,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module,
                "_read_json",
                AsyncMock(
                    return_value={
                        "method": "yookassa",
                        "months": 1,
                        "tariff_key": "standard",
                        "sale_mode": "subscription",
                        "renew_hwid_devices": True,
                    }
                ),
            ),
            patch.object(
                billing_module,
                "_get_cached_webapp_settings",
                return_value={"subscription_options": {}, "stars_subscription_options": {}},
            ),
            patch.object(
                billing_module.user_dal,
                "get_user_by_id",
                AsyncMock(return_value=db_user),
            ),
            patch.object(
                billing_module,
                "_create_subscription_payment",
                AsyncMock(side_effect=_fake_create_payment),
            ) as create_payment,
        ):
            response = await billing_module.create_payment_route(request)

        self.assertEqual(response.status, 200)
        payload = json.loads(response.text)
        self.assertEqual(payload["price"], 150)
        self.assertEqual(payload["hwid_device_count"], 1)
        subscription_service.quote_hwid_device_renewal_for_subscription.assert_awaited_once_with(
            ANY,
            user_id=42,
            target_tariff_key="standard",
            months=1,
            currency="rub",
        )
        create_payment.assert_awaited_once()

    async def test_create_payment_route_rejects_fractional_hwid_device_count(self):
        tariff = SimpleNamespace(
            key="standard",
            billing_model="period",
            enabled_periods=[1],
            hwid_device_packages=SimpleNamespace(
                rub=[SimpleNamespace(count=1)],
                stars=[],
            ),
        )
        settings = SimpleNamespace(
            traffic_sale_mode=False,
            tariffs_config=SimpleNamespace(require=lambda key: tariff),
            DEFAULT_LANGUAGE="en",
            DEFAULT_CURRENCY_SYMBOL="RUB",
        )
        subscription_service = SimpleNamespace(quote_hwid_device_topup=AsyncMock())
        request = SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _SessionFactory(),
                "subscription_service": subscription_service,
            }
        )

        with (
            patch.object(billing_module, "_require_user_id", return_value=42),
            patch.object(
                billing_module,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value=None),
            ),
            patch.object(
                billing_module,
                "_read_json",
                AsyncMock(
                    return_value={
                        "method": "yookassa",
                        "months": 1.9,
                        "device_count": 1.9,
                        "tariff_key": "standard",
                        "sale_mode": "hwid_devices",
                    }
                ),
            ),
            patch.object(
                billing_module,
                "_get_cached_webapp_settings",
                return_value={"subscription_options": {}, "stars_subscription_options": {}},
            ),
        ):
            response = await billing_module.create_payment_route(request)

        self.assertEqual(response.status, 400)
        payload = json.loads(response.text)
        self.assertEqual(payload["error"], "invalid_plan")
        subscription_service.quote_hwid_device_topup.assert_not_awaited()
