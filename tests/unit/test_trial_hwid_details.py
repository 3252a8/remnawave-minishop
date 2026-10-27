"""Trial device limits survive panel refreshes and local profile reads."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from bot.app.web.webapp.devices import _load_devices_payload
from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService
from config.settings import Settings
from db.models import Subscription, User


@pytest.mark.parametrize("mode", ["panel", "local", "panel_failure"])
@pytest.mark.parametrize(
    "general_limit,trial_limit,override,extra,expected",
    [
        (5, 1, None, 0, 1),
        (0, 1, None, 0, 1),
        (None, 1, None, 0, 1),
        (5, 0, None, 0, 0),
        (5, None, None, 0, 0),
        (5, 1, 3, 1, 4),
        (5, 1, 0, 1, 0),
        (5, 1, None, 2, 3),
    ],
)
def test_trial_device_payload_uses_trial_limit(
    mode, general_limit, trial_limit, override, extra, expected
):
    async def scenario():
        settings = Settings(
            _env_file=None,
            BOT_TOKEN="token",
            POSTGRES_USER="app_user",
            POSTGRES_PASSWORD="app_password",
            USER_HWID_DEVICE_LIMIT=general_limit,
            TRIAL_HWID_DEVICE_LIMIT=trial_limit,
        )
        panel = AsyncMock(spec=PanelApiService)
        panel.get_user_by_uuid_lookup.return_value = {
            "ok": mode != "panel_failure",
            "user": (
                {
                    "uuid": "panel-user",
                    "shortUuid": "short-uuid",
                    "status": "ACTIVE",
                    "expireAt": "2099-02-01T00:00:00Z",
                    "subscriptionUrl": "https://panel.example.test/sub/short-uuid",
                    "hwidDeviceLimit": expected,
                }
                if mode != "panel_failure"
                else None
            ),
            "reason": "timeout" if mode == "panel_failure" else None,
        }
        panel.get_user_devices.return_value = [{"hwid": "one-device"}]
        service = SubscriptionService(settings, panel)
        now = datetime.now(UTC)
        user = User(user_id=42, panel_user_uuid="panel-user", language_code="en")
        sub = Subscription(
            subscription_id=7,
            user_id=42,
            panel_user_uuid="panel-user",
            panel_subscription_uuid="short-uuid",
            start_date=now,
            end_date=now + timedelta(days=3),
            is_active=True,
            provider="trial",
            status_from_panel="TRIAL",
            hwid_device_limit=trial_limit if override is None else override,
            hwid_device_limit_is_override=override is not None,
            extra_hwid_devices=extra,
        )
        session = AsyncMock()
        with (
            patch(
                "bot.services.subscription_service_impl.lifecycle_details.user_dal.get_user_by_id",
                AsyncMock(return_value=user),
            ),
            patch(
                "bot.services.subscription_service_impl.lifecycle_details.subscription_dal.get_active_subscription_by_user_id",
                AsyncMock(return_value=sub),
            ),
            patch(
                "bot.services.subscription_service_impl.lifecycle_details.subscription_dal.update_subscription",
                AsyncMock(),
            ),
            patch(
                "bot.services.subscription_service_impl.lifecycle_details.tariff_dal.get_hwid_device_entitlement_summary",
                AsyncMock(return_value={"active_devices": extra}),
            ),
            patch(
                "bot.app.web.webapp.devices.device_name_dal.get_device_names",
                AsyncMock(return_value={}),
            ),
        ):
            if mode == "local":
                details = await service.get_active_subscription_details(
                    session, 42, prefer_local=True
                )
                assert details is not None
                assert details["max_devices"] == expected
                assert details["base_hwid_device_limit"] == (
                    trial_limit if override is None else override
                )
            else:
                result = await _load_devices_payload(service, session, 42)
                assert result["ok"] is True
                assert result["payload"]["current_devices"] == 1
                assert result["payload"]["max_devices"] == expected
                panel.get_user_by_uuid_lookup.assert_awaited_once_with(
                    "panel-user", log_response=False
                )

    asyncio.run(scenario())
