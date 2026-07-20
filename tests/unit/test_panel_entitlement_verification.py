import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot.services.panel_api_service import PanelApiService
from bot.services.subscription_service_impl.core import SubscriptionService


def _panel_user(*, squads: list[str] | None = None, traffic_limit: int = 200) -> dict:
    return {
        "uuid": "panel-user",
        "expireAt": "2099-02-01T00:00:00.000Z",
        "trafficLimitBytes": traffic_limit,
        "trafficLimitStrategy": "NO_RESET",
        "hwidDeviceLimit": 5,
        "activeInternalSquads": squads if squads is not None else ["pro"],
        "externalSquadUuid": "external",
        "status": "ACTIVE",
    }


def _expected_entitlement() -> dict:
    return {
        "uuid": "panel-user",
        "expireAt": "2099-02-01T00:00:00.000Z",
        "trafficLimitBytes": 200,
        "trafficLimitStrategy": "NO_RESET",
        "hwidDeviceLimit": 5,
        "activeInternalSquads": ["pro"],
        "externalSquadUuid": "external",
        "status": "ACTIVE",
    }


class PanelEntitlementVerificationTests(unittest.IsolatedAsyncioTestCase):
    def _service(self) -> tuple[SubscriptionService, AsyncMock]:
        panel_service = AsyncMock(spec=PanelApiService)
        service = SubscriptionService(SimpleNamespace(), panel_service)
        return service, panel_service

    async def test_missing_patch_response_accepts_exact_fresh_panel_state(self):
        service, panel_service = self._service()
        persisted_user = _panel_user()
        panel_service.get_user_by_uuid = AsyncMock(return_value=persisted_user)

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            None,
            _expected_entitlement(),
            source="paid_activation",
        )

        self.assertEqual(confirmed, persisted_user)
        panel_service.get_user_by_uuid.assert_awaited_once_with(
            "panel-user",
            log_response=False,
            use_cache=False,
        )

    async def test_matching_patch_response_still_requires_fresh_panel_state(self):
        service, panel_service = self._service()
        patch_user = _panel_user()
        persisted_user = _panel_user()
        panel_service.get_user_by_uuid = AsyncMock(return_value=persisted_user)

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            patch_user,
            _expected_entitlement(),
            source="paid_activation",
        )

        self.assertEqual(confirmed, persisted_user)
        panel_service.get_user_by_uuid.assert_awaited_once_with(
            "panel-user",
            log_response=False,
            use_cache=False,
        )

    async def test_transient_stale_state_is_repaired_and_rechecked(self):
        service, panel_service = self._service()
        stale_user = _panel_user(traffic_limit=100)
        persisted_user = _panel_user()
        panel_service.get_user_by_uuid = AsyncMock(side_effect=[stale_user, persisted_user])
        panel_service.update_user_details_on_panel = AsyncMock(return_value=persisted_user)

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            persisted_user,
            _expected_entitlement(),
            source="paid_activation",
            retry_delay_seconds=0,
        )

        self.assertEqual(confirmed, persisted_user)
        self.assertEqual(panel_service.get_user_by_uuid.await_count, 2)
        panel_service.update_user_details_on_panel.assert_awaited_once_with(
            "panel-user",
            _expected_entitlement(),
        )

    async def test_transient_read_failure_is_repaired_and_rechecked(self):
        service, panel_service = self._service()
        persisted_user = _panel_user()
        panel_service.get_user_by_uuid = AsyncMock(
            side_effect=[RuntimeError("panel read failed"), persisted_user]
        )
        panel_service.update_user_details_on_panel = AsyncMock(return_value=persisted_user)

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            persisted_user,
            _expected_entitlement(),
            source="paid_activation",
            retry_delay_seconds=0,
        )

        self.assertEqual(confirmed, persisted_user)
        self.assertEqual(panel_service.get_user_by_uuid.await_count, 2)
        panel_service.update_user_details_on_panel.assert_awaited_once_with(
            "panel-user",
            _expected_entitlement(),
        )

    async def test_truthy_stale_response_and_stale_get_are_rejected(self):
        service, panel_service = self._service()
        stale_user = _panel_user(traffic_limit=100)
        panel_service.get_user_by_uuid = AsyncMock(return_value=stale_user)
        panel_service.update_user_details_on_panel = AsyncMock(return_value=_panel_user())

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            stale_user,
            _expected_entitlement(),
            source="paid_activation",
            retry_delay_seconds=0,
        )

        self.assertIsNone(confirmed)
        self.assertEqual(panel_service.get_user_by_uuid.await_count, 3)
        self.assertEqual(panel_service.update_user_details_on_panel.await_count, 2)

    async def test_tariff_switch_rejects_old_squads_when_expiry_is_unchanged(self):
        service, panel_service = self._service()
        stale_user = _panel_user(squads=["basic"])
        panel_service.get_user_by_uuid = AsyncMock(return_value=stale_user)

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            stale_user,
            _expected_entitlement(),
            source="tariff_switch",
            retry_delay_seconds=0,
        )

        self.assertIsNone(confirmed)

    async def test_create_wrapper_with_wrong_external_squad_is_rejected(self):
        service, panel_service = self._service()
        wrong_created_user = _panel_user()
        wrong_created_user["externalSquadUuid"] = "stale-external"
        panel_service.get_user_by_uuid = AsyncMock(return_value=wrong_created_user)

        confirmed = await service._confirmed_panel_entitlement(
            "panel-user",
            {"response": wrong_created_user},
            _expected_entitlement(),
            source="paid_activation_create",
            retry_delay_seconds=0,
        )

        self.assertIsNone(confirmed)


if __name__ == "__main__":
    unittest.main()
