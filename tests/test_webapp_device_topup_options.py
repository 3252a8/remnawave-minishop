import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

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
