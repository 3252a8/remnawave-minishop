"""A snapshot used to prove absence must be fresh and complete."""

import time
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from bot.services.panel_api_compat import PanelApiCompatibility
from bot.services.panel_api_service import PanelApiService
from tests.support.settings_stub import settings_stub


class PanelIdentitySnapshotTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.panel = PanelApiService(
            settings_stub(
                PANEL_API_URL="https://panel.example.test/api",
                PANEL_ALL_USERS_PAGE_DELAY_SECONDS=0,
            )
        )
        self.panel._panel_api_compatibility = PanelApiCompatibility.from_metadata(
            {"response": {"version": "3.4.5"}}
        )
        self.panel._panel_api_compatibility_detected_at = time.monotonic()

    async def test_empty_cached_snapshot_does_not_hide_a_new_profile(self):
        self.panel._request = AsyncMock(
            side_effect=[
                {"response": {"users": []}},
                {"response": {"users": [{"id": 42, "username": "tg_42"}]}},
            ]
        )
        self.assertEqual(await self.panel.get_all_panel_users(), [])
        self.assertEqual(await self.panel.get_all_panel_users(), [])
        fresh = await self.panel.get_all_panel_users(use_cache=False)
        self.assertEqual(fresh, [{"uuid": "42", "id": 42, "username": "tg_42"}])
        self.assertEqual(self.panel._request.await_count, 2)

    async def test_incomplete_stream_never_confirms_absence(self):
        first_page = {"response": {"users": [{"id": 99}], "nextCursor": "next"}}
        cases = (
            {"response": {"users": [{"id": 100}], "nextCursor": "next"}},
            {"response": {"users": [], "nextCursor": "next"}},
            {"response": {"users": [{"id": 100}, "invalid-user"]}},
            {"error": True, "status_code": 503},
            {"error": True, "status_code": 401},
            {"response": {}},
        )
        for second_page in cases:
            with self.subTest(second_page=second_page):
                self.setUp()
                self.panel._request = AsyncMock(side_effect=[first_page, second_page])
                self.assertIsNone(
                    await self.panel.get_all_panel_users(page_size=100, use_cache=False)
                )
                self.assertEqual(self.panel._request.await_count, 2)

    async def test_incompatible_reference_is_not_reported_as_a_confirmed_deletion(self):
        self.panel._request = AsyncMock()
        lookup = await self.panel.get_user_by_uuid_lookup("legacy-uuid")
        self.assertTrue(lookup["reference_incompatible"])
        self.assertFalse(lookup["not_found"])
        self.assertFalse(lookup["ok"])
        self.panel._request.assert_not_awaited()
