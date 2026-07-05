import json
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web.admin_api_impl import broadcast as broadcast_module
from bot.app.web.admin_api_impl import common as common_module
from bot.app.web.admin_api_impl import users as users_module
from bot.app.web.admin_api_impl import users_detail
from tests.support.settings_stub import settings_stub


class FakeResult:
    def __init__(self, rows=None):
        self._rows = rows or []

    def all(self):
        return self._rows

    def scalars(self):
        return self


class FakeSession:
    def __init__(self):
        self.execute = AsyncMock(side_effect=[FakeResult([]), FakeResult([]), FakeResult([])])
        self.committed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        pass


def _active_subscription(panel_user_uuid="panel-from-sub"):
    return SimpleNamespace(
        subscription_id=10,
        panel_user_uuid=panel_user_uuid,
        panel_subscription_uuid=None,
        start_date=datetime(2026, 6, 1, tzinfo=UTC),
        end_date=datetime(2026, 7, 1, tzinfo=UTC),
        duration_months=1,
        is_active=True,
        status_from_panel="ACTIVE",
        traffic_limit_bytes=100,
        traffic_used_bytes=0,
        tier_baseline_bytes=0,
        topup_balance_bytes=0,
        premium_used_bytes=0,
        premium_baseline_bytes=0,
        premium_topup_balance_bytes=0,
        premium_topup_used_bytes=0,
        premium_bonus_bytes=0,
        regular_bonus_bytes=0,
        regular_unlimited_override=False,
        premium_unlimited_override=False,
        premium_is_limited=False,
        tariff_key="standard",
        auto_renew_enabled=True,
        provider="yookassa",
        is_throttled=False,
    )


class AdminPanelActivityTests(unittest.IsolatedAsyncioTestCase):
    def test_panel_activity_detects_connected_and_never_connected_users(self):
        self.assertEqual(
            common_module._panel_user_connection_activity(
                {"userTraffic": {"onlineAt": "2026-06-05T12:00:00Z"}}
            ),
            {
                "status": "connected",
                "last_connected_at": "2026-06-05T12:00:00+00:00",
            },
        )
        self.assertEqual(
            common_module._panel_user_connection_activity(
                {
                    "userTraffic": {
                        "onlineAt": None,
                        "firstConnectedAt": None,
                        "lastConnectedNodeUuid": None,
                        "lifetimeUsedTrafficBytes": 0,
                    },
                }
            ),
            {"status": "never", "last_connected_at": None},
        )
        self.assertEqual(
            common_module._panel_user_connection_activity(
                {"userTraffic": {"lifetimeUsedTrafficBytes": 1024}}
            ),
            {"status": "connected", "last_connected_at": None},
        )

    async def test_active_never_connected_audience_uses_panel_status(self):
        session = SimpleNamespace(
            execute=AsyncMock(
                return_value=FakeResult(
                    [
                        (1, "never-panel"),
                        (2, "connected-panel"),
                        (3, "missing-panel"),
                        (4, "also-never-panel"),
                        (4, "also-connected-panel"),
                    ]
                )
            )
        )

        async def get_user_by_uuid(panel_uuid):
            return {
                "never-panel": {
                    "userTraffic": {
                        "onlineAt": None,
                        "firstConnectedAt": None,
                        "lastConnectedNodeUuid": None,
                    },
                },
                "connected-panel": {"userTraffic": {"onlineAt": "2026-06-05T12:00:00Z"}},
                "also-never-panel": {
                    "userTraffic": {
                        "onlineAt": None,
                        "firstConnectedAt": None,
                        "lastConnectedNodeUuid": None,
                    },
                },
                "also-connected-panel": {
                    "userTraffic": {"lifetimeUsedTrafficBytes": 1},
                },
            }.get(panel_uuid)

        panel_service = SimpleNamespace(get_user_by_uuid=AsyncMock(side_effect=get_user_by_uuid))

        result = await broadcast_module._user_ids_with_active_subscription_never_connected(
            session,
            panel_service,
        )

        self.assertEqual(result, [1])
        self.assertEqual(
            [call.args[0] for call in panel_service.get_user_by_uuid.await_args_list],
            [
                "never-panel",
                "connected-panel",
                "missing-panel",
                "also-never-panel",
                "also-connected-panel",
            ],
        )

    async def test_user_detail_includes_last_vpn_connection_from_panel(self):
        session = FakeSession()
        user = SimpleNamespace(
            user_id=42,
            telegram_id=42,
            telegram_photo_url=None,
            username="alice",
            first_name="Alice",
            last_name=None,
            email=None,
            language_code="ru",
            is_banned=False,
            registration_date=datetime(2026, 6, 1, tzinfo=UTC),
            panel_user_uuid=None,
            referral_code=None,
            referred_by_id=None,
            trial_eligibility_reset_at=None,
        )
        active_sub = _active_subscription("panel-from-sub")
        panel_service = SimpleNamespace(
            get_user_by_uuid=AsyncMock(
                return_value={
                    "subscriptionUrl": "https://panel.example/sub/short",
                    "userTraffic": {"onlineAt": "2026-06-05T12:00:00Z"},
                }
            )
        )
        install_links = AsyncMock(return_value="https://app.example/s/share")
        request = SimpleNamespace(
            app={
                "settings": settings_stub(SUBSCRIPTION_MINI_APP_URL=None),
                "async_session_factory": lambda: session,
                "subscription_service": SimpleNamespace(panel_service=panel_service),
            },
            match_info={"user_id": "42"},
        )

        with (
            patch.object(users_detail, "_require_admin_user_id", return_value=100),
            patch.object(users_module.user_dal, "get_user_by_id", AsyncMock(return_value=user)),
            patch.object(
                users_module.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=active_sub),
            ),
            patch.object(
                users_module.payment_dal,
                "get_user_total_paid",
                AsyncMock(return_value=0),
            ),
            patch.object(
                users_module.message_log_dal,
                "count_user_message_logs",
                AsyncMock(return_value=0),
            ),
            patch.object(
                users_module.user_dal,
                "get_referrer_for_user",
                AsyncMock(return_value=None),
            ),
            patch.object(
                users_module.user_dal,
                "count_users_referred_by",
                AsyncMock(return_value=0),
            ),
            patch.object(users_detail, "_bulk_user_avatar_keys", AsyncMock(return_value={})),
            patch.object(
                users_module.user_dal,
                "ensure_referral_code",
                AsyncMock(return_value="REF"),
            ),
            patch.object(users_detail, "ensure_user_install_guide_share_url", install_links),
        ):
            response = await users_module.admin_user_detail_route(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["subscription_url"], "https://panel.example/sub/short")
        self.assertEqual(payload["install_share_url"], "https://app.example/s/share")
        self.assertEqual(payload["vpn_connection_status"], "connected")
        self.assertEqual(payload["last_vpn_connected_at"], "2026-06-05T12:00:00+00:00")
        panel_service.get_user_by_uuid.assert_awaited_once_with("panel-from-sub")
        install_links.assert_awaited_once()
        self.assertIs(install_links.await_args.kwargs["local_subscription"], active_sub)


if __name__ == "__main__":
    unittest.main()
