import asyncio
import json
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from bot.app.web import subscription_webapp as guides
from config.subscription_guides_config import default_subscription_guides_config_text


class _AsyncSessionFactory:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class SubscriptionGuidesRouteTests(unittest.IsolatedAsyncioTestCase):
    def _request(self, settings, panel_service, match_info=None):
        return SimpleNamespace(
            app={
                "settings": settings,
                "async_session_factory": _AsyncSessionFactory(),
                "panel_service": panel_service,
                "subscription_guides_config_cache": {"fingerprint": None, "status": None},
                "subscription_guides_config_lock": asyncio.Lock(),
            },
            match_info=match_info or {},
            headers={"User-Agent": "Mozilla/5.0", "Host": "app.example.test"},
            host="app.example.test",
            scheme="https",
        )

    def _settings(self, **overrides):
        values = {
            "SUBSCRIPTION_GUIDES_ENABLED": True,
            "SUBSCRIPTION_PAGE_CONFIG_PANEL_ENABLED": True,
            "SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED": False,
            "SUBSCRIPTION_PAGE_CONFIG_JSON": "",
            "SUBSCRIPTION_PAGE_CONFIG_PATH": "data/subpage-config/multiapp.json",
            "SUBSCRIPTION_MINI_APP_URL": "https://app.example.test",
            "CRYPT4_ENABLED": False,
            "CRYPT4_REDIRECT_URL": "",
            "CRYPT4_LINK_CACHE_TTL_SECONDS": 3600,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def _auth_patch(self):
        return patch.dict(
            guides.subscription_guides_route.__globals__,
            {"_require_user_id": lambda _: 42},
        )

    async def test_uses_panel_config_when_admin_json_is_empty(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={
                    "uuid": default_uuid,
                    "config": json.loads(default_subscription_guides_config_text()),
                }
            ),
        )
        request = self._request(self._settings(), panel_service)

        with self._auth_patch():
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["source"], "panel")
        self.assertEqual(body["config"]["version"], "1")
        self.assertEqual(response.headers["Cache-Control"], "private, max-age=60")
        panel_service.get_subscription_page_config_list.assert_awaited_once()
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(default_uuid)

    async def test_route_returns_compact_utf8_config_payload(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        panel_config = json.loads(default_subscription_guides_config_text())
        panel_config["svgLibrary"]["UnusedIcon"] = (
            '<svg viewBox="0 0 1 1"><path d="M0 0h1v1H0z"/></svg>'
        )
        panel_config["baseTranslations"]["installationGuideHeader"]["ru"] = "Инструкция"
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": default_uuid, "config": panel_config}
            ),
        )
        request = self._request(self._settings(), panel_service)

        with self._auth_patch():
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertIn("Инструкция", response.text)
        self.assertNotIn("\\u0418", response.text)
        self.assertNotIn("UnusedIcon", body["config"]["svgLibrary"])
        self.assertIn(
            body["config"]["platforms"]["windows"]["svgIconKey"],
            body["config"]["svgLibrary"],
        )

    async def test_uses_resolved_panel_config_for_active_user_subscription(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        custom_uuid = "11111111-1111-1111-1111-111111111111"
        resolved_config = json.loads(default_subscription_guides_config_text())
        resolved_config["platforms"]["windows"]["apps"][0]["name"] = "External Squad App"
        panel_service = SimpleNamespace(
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "user-short",
                    "subscriptionUrl": "https://sb.example.test/user-short",
                    "username": "demo",
                }
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": custom_uuid, "webpageAllowed": True}
            ),
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": custom_uuid, "config": resolved_config}
            ),
        )
        request = self._request(self._settings(), panel_service)
        db_user = SimpleNamespace(panel_user_uuid="panel-user")
        local_sub = SimpleNamespace(panel_subscription_uuid="user-short")

        with (
            self._auth_patch(),
            patch.object(guides.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                guides.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=local_sub),
            ),
        ):
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["source"], "panel")
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("External Squad App", windows_apps)
        panel_service.get_user_by_uuid.assert_not_called()
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        call = panel_service.get_subscription_page_config_by_short_uuid.await_args
        self.assertEqual(call.args, ("user-short",))
        self.assertEqual(call.kwargs["request_headers"]["host"], "app.example.test")
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(custom_uuid)
        panel_service.get_subscription_page_config_list.assert_not_called()

    async def test_uses_external_squad_config_when_short_uuid_response_has_no_uuid(self):
        custom_uuid = "11111111-1111-1111-1111-111111111111"
        resolved_config = json.loads(default_subscription_guides_config_text())
        resolved_config["platforms"]["windows"]["apps"][0]["name"] = "External Squad App"
        panel_service = SimpleNamespace(
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "user-short",
                    "externalSquadUuid": "external-squad",
                }
            ),
            get_external_squad=AsyncMock(
                return_value={"uuid": "external-squad", "subpageConfigUuid": custom_uuid}
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": None, "webpageAllowed": True}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": custom_uuid, "config": resolved_config}
            ),
            get_subscription_page_config_list=AsyncMock(),
        )
        request = self._request(self._settings(), panel_service)
        db_user = SimpleNamespace(panel_user_uuid="panel-user")
        local_sub = SimpleNamespace(panel_subscription_uuid="user-short")

        with (
            self._auth_patch(),
            patch.object(guides.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                guides.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=local_sub),
            ),
        ):
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("External Squad App", windows_apps)
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        panel_service.get_user_by_uuid.assert_awaited_once_with("panel-user")
        panel_service.get_external_squad.assert_awaited_once_with("external-squad")
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(custom_uuid)
        panel_service.get_subscription_page_config_list.assert_not_called()

    async def test_resolved_panel_config_is_cached_for_same_short_uuid(self):
        custom_uuid = "11111111-1111-1111-1111-111111111111"
        resolved_config = json.loads(default_subscription_guides_config_text())
        resolved_config["platforms"]["windows"]["apps"][0]["name"] = "Cached External App"
        panel_service = SimpleNamespace(
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "user-short",
                    "subscriptionUrl": "https://sb.example.test/user-short",
                }
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": custom_uuid, "webpageAllowed": True}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": custom_uuid, "config": resolved_config}
            ),
            get_subscription_page_config_list=AsyncMock(),
        )
        request = self._request(self._settings(), panel_service)
        db_user = SimpleNamespace(panel_user_uuid="panel-user")
        local_sub = SimpleNamespace(panel_subscription_uuid="user-short")

        with (
            self._auth_patch(),
            patch.object(guides.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                guides.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=local_sub),
            ),
        ):
            response = await guides.subscription_guides_route(request)
            second_response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        second_body = json.loads(second_response.text)
        self.assertTrue(body["enabled"])
        self.assertTrue(second_body["enabled"])
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("Cached External App", windows_apps)
        self.assertEqual(body["config"], second_body["config"])
        panel_service.get_user_by_uuid.assert_not_called()
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(custom_uuid)
        panel_service.get_subscription_page_config_list.assert_not_called()

    async def test_panel_config_uuid_cache_is_shared_between_short_uuids(self):
        custom_uuid = "11111111-1111-1111-1111-111111111111"
        resolved_config = json.loads(default_subscription_guides_config_text())
        resolved_config["platforms"]["windows"]["apps"][0]["name"] = "Shared Config App"
        panel_service = SimpleNamespace(
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": custom_uuid, "webpageAllowed": True}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": custom_uuid, "config": resolved_config}
            ),
            get_subscription_page_config_list=AsyncMock(),
        )
        request = self._request(self._settings(), panel_service)

        first = await guides._subscription_guides_status_from_panel_short_uuid_cached(
            request.app,
            request.app["settings"],
            "short-one",
            panel_user_uuid="panel-user-one",
            request_headers={"host": "app.example.test"},
        )
        second = await guides._subscription_guides_status_from_panel_short_uuid_cached(
            request.app,
            request.app["settings"],
            "short-two",
            panel_user_uuid="panel-user-two",
            request_headers={"host": "app.example.test"},
        )

        self.assertTrue(first["enabled"])
        self.assertTrue(second["enabled"])
        windows_apps = [app["name"] for app in second["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("Shared Config App", windows_apps)
        self.assertEqual(panel_service.get_subscription_page_config_by_short_uuid.await_count, 2)
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(custom_uuid)
        panel_service.get_subscription_page_config_list.assert_not_called()

    async def test_admin_json_override_takes_priority_over_panel(self):
        admin_config = json.loads(default_subscription_guides_config_text())
        panel_service = SimpleNamespace(get_subscription_page_config_by_uuid=AsyncMock())
        request = self._request(
            self._settings(
                SUBSCRIPTION_PAGE_CONFIG_JSON_OVERRIDE_ENABLED=True,
                SUBSCRIPTION_PAGE_CONFIG_JSON=json.dumps(admin_config),
            ),
            panel_service,
        )

        with self._auth_patch():
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["source"], "admin_json")
        panel_service.get_subscription_page_config_by_uuid.assert_not_called()

    async def test_admin_json_is_ignored_until_override_switch_is_enabled(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        admin_config = json.loads(default_subscription_guides_config_text())
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={
                    "uuid": default_uuid,
                    "config": json.loads(default_subscription_guides_config_text()),
                }
            ),
        )
        request = self._request(
            self._settings(SUBSCRIPTION_PAGE_CONFIG_JSON=json.dumps(admin_config)),
            panel_service,
        )

        with self._auth_patch():
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["source"], "panel")
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(default_uuid)

    async def test_resolved_panel_config_falls_back_to_default_panel_config(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        default_config = json.loads(default_subscription_guides_config_text())
        default_config["platforms"]["windows"]["apps"][0]["name"] = "Default App"
        panel_service = SimpleNamespace(
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "user-short",
                    "subscriptionUrl": "https://sb.example.test/user-short",
                }
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(return_value=None),
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": default_uuid, "config": default_config}
            ),
        )
        request = self._request(self._settings(), panel_service)
        db_user = SimpleNamespace(panel_user_uuid="panel-user")
        local_sub = SimpleNamespace(panel_subscription_uuid=None)

        with (
            self._auth_patch(),
            patch.object(guides.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                guides.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=local_sub),
            ),
        ):
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("Default App", windows_apps)
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        panel_service.get_subscription_page_config_list.assert_awaited_once()
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(default_uuid)

    async def test_missing_subpage_config_uses_panel_default_config(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        default_config = json.loads(default_subscription_guides_config_text())
        windows_apps = json.loads(json.dumps(default_config["platforms"]["windows"]["apps"][:3]))
        for app, name in zip(windows_apps, ("INCY", "Happ", "Throne")):
            app["name"] = name
        default_config["platforms"]["windows"]["apps"] = windows_apps
        panel_service = SimpleNamespace(
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "user-short",
                    "subscriptionUrl": "https://sb.example.test/user-short",
                    "externalSquadUuid": None,
                }
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": None, "webpageAllowed": False}
            ),
            get_subscription_page_config_list=AsyncMock(
                return_value={
                    "configs": [
                        {"uuid": default_uuid, "name": "Default", "viewPosition": 1},
                        {
                            "uuid": "461ff225-4e46-4828-b48f-655b91ba4d49",
                            "name": "ExternalSquadSubPage",
                            "viewPosition": 3,
                        },
                    ]
                }
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": default_uuid, "config": default_config}
            ),
        )
        request = self._request(self._settings(), panel_service)
        db_user = SimpleNamespace(panel_user_uuid="panel-user")
        local_sub = SimpleNamespace(panel_subscription_uuid="user-short")

        with (
            self._auth_patch(),
            patch.object(guides.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)),
            patch.object(
                guides.subscription_dal,
                "get_active_subscription_by_user_id",
                AsyncMock(return_value=local_sub),
            ),
        ):
            response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertEqual(body["source"], "panel")
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertEqual(windows_apps, ["INCY", "Happ", "Throne"])
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        panel_service.get_user_by_uuid.assert_awaited_once_with("panel-user")
        panel_service.get_subscription_page_config_list.assert_awaited_once()
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(default_uuid)

    async def test_panel_config_is_cached_for_multiple_users(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        panel_config = json.loads(default_subscription_guides_config_text())
        panel_config["platforms"]["windows"]["apps"][0]["name"] = "Throne"
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": default_uuid, "config": panel_config}
            ),
        )
        request = self._request(self._settings(), panel_service)

        with self._auth_patch():
            response = await guides.subscription_guides_route(request)
            second_response = await guides.subscription_guides_route(request)

        body = json.loads(response.text)
        second_body = json.loads(second_response.text)
        self.assertTrue(body["enabled"])
        self.assertTrue(second_body["enabled"])
        self.assertEqual(body["source"], "panel")
        self.assertEqual(body["config"]["version"], "1")
        self.assertIn("windows", body["config"]["platforms"])
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("Throne", windows_apps)
        panel_service.get_subscription_page_config_list.assert_awaited_once()
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(default_uuid)

    async def test_public_route_returns_resolved_config_and_subscription_payload(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        custom_uuid = "11111111-1111-1111-1111-111111111111"
        share_token = "8f559061460e8fede78ef18dce887236"
        panel_config = json.loads(default_subscription_guides_config_text())
        panel_config["platforms"]["windows"]["apps"][0]["name"] = "Shared App"
        resolved_config = json.loads(default_subscription_guides_config_text())
        resolved_config["platforms"]["windows"]["apps"][0]["name"] = "Shared External App"
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                side_effect=lambda uuid: {
                    "uuid": uuid,
                    "config": resolved_config if uuid == custom_uuid else panel_config,
                }
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": custom_uuid, "webpageAllowed": True}
            ),
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "share-short",
                    "subscriptionUrl": "https://sb.example.test/share-short",
                    "username": "demo",
                }
            ),
        )
        request = self._request(
            self._settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.test/app"),
            panel_service,
            match_info={"share_token": share_token},
        )
        local_sub = SimpleNamespace(
            panel_user_uuid="panel-user",
            install_share_token=share_token,
            is_active=True,
            end_date=datetime.now(timezone.utc) + timedelta(days=3),
        )

        with patch.object(
            guides.subscription_dal,
            "get_subscription_by_install_share_token",
            AsyncMock(return_value=local_sub),
        ):
            response = await guides.public_subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertTrue(body["enabled"])
        self.assertEqual(response.headers["Cache-Control"], "private, max-age=60")
        self.assertEqual(body["subscription"]["config_link"], "https://sb.example.test/share-short")
        self.assertEqual(
            body["subscription"]["share_url"],
            f"https://app.example.test/s/{share_token}",
        )
        self.assertEqual(body["subscription"]["install_share_token"], share_token)
        panel_service.get_user_by_uuid.assert_awaited_once_with("panel-user")
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        call = panel_service.get_subscription_page_config_by_short_uuid.await_args
        self.assertEqual(call.args, ("share-short",))
        self.assertEqual(call.kwargs["request_headers"]["host"], "app.example.test")
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(custom_uuid)
        panel_service.get_subscription_page_config_list.assert_not_called()
        windows_apps = [app["name"] for app in body["config"]["platforms"]["windows"]["apps"]]
        self.assertIn("Shared External App", windows_apps)

    async def test_public_route_caches_active_subscription_payload(self):
        default_uuid = "00000000-0000-0000-0000-000000000000"
        custom_uuid = "11111111-1111-1111-1111-111111111111"
        share_token = "8f559061460e8fede78ef18dce887236"
        resolved_config = json.loads(default_subscription_guides_config_text())
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(
                return_value={"configs": [{"uuid": default_uuid, "viewPosition": 1}]}
            ),
            get_subscription_page_config_by_uuid=AsyncMock(
                return_value={"uuid": custom_uuid, "config": resolved_config}
            ),
            get_subscription_page_config_by_short_uuid=AsyncMock(
                return_value={"subpageConfigUuid": custom_uuid, "webpageAllowed": True}
            ),
            get_user_by_uuid=AsyncMock(
                return_value={
                    "shortUuid": "share-short",
                    "subscriptionUrl": "https://sb.example.test/share-short",
                    "username": "demo",
                }
            ),
        )
        request = self._request(
            self._settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.test/app"),
            panel_service,
            match_info={"share_token": share_token},
        )
        local_sub = SimpleNamespace(
            panel_user_uuid="panel-user",
            install_share_token=share_token,
            is_active=True,
            end_date=datetime.now(timezone.utc) + timedelta(days=3),
        )
        get_sub = AsyncMock(return_value=local_sub)

        with patch.object(
            guides.subscription_dal,
            "get_subscription_by_install_share_token",
            get_sub,
        ):
            response = await guides.public_subscription_guides_route(request)
            second_response = await guides.public_subscription_guides_route(request)

        body = json.loads(response.text)
        second_body = json.loads(second_response.text)
        self.assertTrue(body["enabled"])
        self.assertTrue(second_body["enabled"])
        self.assertEqual(body["subscription"], second_body["subscription"])
        get_sub.assert_awaited_once_with(unittest.mock.ANY, share_token)
        panel_service.get_user_by_uuid.assert_awaited_once_with("panel-user")
        panel_service.get_subscription_page_config_by_short_uuid.assert_awaited_once()
        panel_service.get_subscription_page_config_by_uuid.assert_awaited_once_with(custom_uuid)
        panel_service.get_subscription_page_config_list.assert_not_called()

    async def test_public_route_rejects_unknown_share_token_without_loading_config(self):
        share_token = "8f559061460e8fede78ef18dce887236"
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(),
            get_subscription_page_config_by_uuid=AsyncMock(),
            get_user_by_uuid=AsyncMock(),
        )
        request = self._request(
            self._settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.test/app"),
            panel_service,
            match_info={"share_token": share_token},
        )

        with patch.object(
            guides.subscription_dal,
            "get_subscription_by_install_share_token",
            AsyncMock(return_value=None),
        ):
            response = await guides.public_subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertEqual(response.status, 404)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "subscription_unavailable")
        self.assertFalse(body["enabled"])
        self.assertIsNone(body["config"])
        self.assertEqual(body["subscription"]["install_share_token"], share_token)
        self.assertFalse(body["subscription"]["active"])
        panel_service.get_subscription_page_config_list.assert_not_called()
        panel_service.get_subscription_page_config_by_uuid.assert_not_called()
        panel_service.get_user_by_uuid.assert_not_called()

    async def test_public_route_rejects_inactive_share_token_without_panel_user_lookup(self):
        share_token = "8f559061460e8fede78ef18dce887236"
        panel_service = SimpleNamespace(
            get_subscription_page_config_list=AsyncMock(),
            get_subscription_page_config_by_uuid=AsyncMock(),
            get_user_by_uuid=AsyncMock(),
        )
        request = self._request(
            self._settings(SUBSCRIPTION_MINI_APP_URL="https://app.example.test/app"),
            panel_service,
            match_info={"share_token": share_token},
        )
        local_sub = SimpleNamespace(
            panel_user_uuid="panel-user",
            install_share_token=share_token,
            is_active=False,
            end_date=datetime.now(timezone.utc) + timedelta(days=3),
        )

        with patch.object(
            guides.subscription_dal,
            "get_subscription_by_install_share_token",
            AsyncMock(return_value=local_sub),
        ):
            response = await guides.public_subscription_guides_route(request)

        body = json.loads(response.text)
        self.assertEqual(response.status, 404)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"], "subscription_unavailable")
        self.assertFalse(body["subscription"]["active"])
        panel_service.get_user_by_uuid.assert_not_called()


if __name__ == "__main__":
    unittest.main()
