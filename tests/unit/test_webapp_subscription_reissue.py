import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import ANY, AsyncMock, patch

import bot.app.web.subscription_webapp  # noqa: F401
from bot.app.web.webapp import subscription_reissue as reissue_module
from bot.app.web.webapp.subscription_reissue import (
    subscription_reissue_feature_enabled,
    subscription_reissue_route,
)


class _SessionFactory:
    def __init__(self, session=None):
        self.session = session if session is not None else AsyncMock()

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _JsonRequest(SimpleNamespace):
    def __init__(self, payload=None, **kwargs):
        super().__init__(**kwargs)
        self._payload = payload if payload is not None else {}

    async def json(self):
        return self._payload


def _settings(**overrides):
    values = {
        "SUBSCRIPTION_REISSUE_ENABLED": True,
        "email_auth_configured": True,
        "DEFAULT_LANGUAGE": "en",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _db_user(email="user@example.test"):
    return SimpleNamespace(
        user_id=42,
        email=email,
        is_banned=False,
        language_code="en",
        panel_user_uuid="panel-uuid",
    )


def _response_body(response):
    return json.loads(response.body.decode())


def test_feature_flag_requires_email_auth():
    assert subscription_reissue_feature_enabled(_settings()) is True
    assert (
        subscription_reissue_feature_enabled(_settings(SUBSCRIPTION_REISSUE_ENABLED=False)) is False
    )
    assert subscription_reissue_feature_enabled(_settings(email_auth_configured=False)) is False


class WebAppSubscriptionReissueRouteTests(IsolatedAsyncioTestCase):
    def _patch_context(
        self,
        *,
        settings,
        subscription_service,
        db_user,
        rate_limited=False,
    ):
        patches = [
            patch.object(reissue_module, "get_settings", return_value=settings),
            patch.object(reissue_module, "get_session_factory", return_value=_SessionFactory()),
            patch.object(
                reissue_module, "get_subscription_service", return_value=subscription_service
            ),
            patch.object(reissue_module, "get_i18n", return_value=None),
            patch.object(reissue_module, "_require_user_id", return_value=42),
            patch.object(
                reissue_module,
                "_enforce_webapp_rate_limit",
                AsyncMock(return_value="rate-limited" if rate_limited else None),
            ),
            patch.object(
                reissue_module.user_dal, "get_user_by_id", AsyncMock(return_value=db_user)
            ),
            patch.object(
                reissue_module,
                "invalidate_webapp_user_caches",
                AsyncMock(),
            ),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    async def test_disabled_feature_returns_404(self):
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(), panel_service=None
        )
        self._patch_context(
            settings=_settings(SUBSCRIPTION_REISSUE_ENABLED=False),
            subscription_service=subscription_service,
            db_user=_db_user(),
        )

        response = await subscription_reissue_route(_JsonRequest())

        assert response.status == 404
        assert _response_body(response)["error"] == "subscription_reissue_disabled"
        subscription_service.get_active_subscription_details.assert_not_awaited()

    async def test_missing_email_returns_400_before_touching_the_panel(self):
        panel_service = SimpleNamespace(revoke_user_subscription=AsyncMock())
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(),
            panel_service=panel_service,
        )
        self._patch_context(
            settings=_settings(),
            subscription_service=subscription_service,
            db_user=_db_user(email=""),
        )

        response = await subscription_reissue_route(_JsonRequest())

        assert response.status == 400
        assert _response_body(response)["error"] == "email_required"
        subscription_service.get_active_subscription_details.assert_not_awaited()
        panel_service.revoke_user_subscription.assert_not_awaited()

    async def test_inactive_subscription_returns_400(self):
        panel_service = SimpleNamespace(revoke_user_subscription=AsyncMock())
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value=None),
            panel_service=panel_service,
        )
        self._patch_context(
            settings=_settings(),
            subscription_service=subscription_service,
            db_user=_db_user(),
        )

        response = await subscription_reissue_route(_JsonRequest())

        assert response.status == 400
        assert _response_body(response)["error"] == "subscription_not_active"
        panel_service.revoke_user_subscription.assert_not_awaited()

    async def test_panel_failure_returns_502_and_skips_email(self):
        panel_service = SimpleNamespace(revoke_user_subscription=AsyncMock(return_value=None))
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value={"user_id": "panel-uuid"}),
            panel_service=panel_service,
        )
        self._patch_context(
            settings=_settings(),
            subscription_service=subscription_service,
            db_user=_db_user(),
        )
        send_email = AsyncMock()
        with patch.object(reissue_module, "send_user_notification_email", send_email):
            response = await subscription_reissue_route(_JsonRequest())

        assert response.status == 502
        assert _response_body(response)["error"] == "subscription_reissue_failed"
        panel_service.revoke_user_subscription.assert_awaited_once_with("panel-uuid")
        send_email.assert_not_awaited()

    async def test_rate_limited_short_circuits(self):
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(), panel_service=None
        )
        self._patch_context(
            settings=_settings(),
            subscription_service=subscription_service,
            db_user=_db_user(),
            rate_limited=True,
        )

        response = await subscription_reissue_route(_JsonRequest())

        assert response == "rate-limited"
        subscription_service.get_active_subscription_details.assert_not_awaited()

    async def test_success_reissues_emails_and_invalidates_caches(self):
        panel_service = SimpleNamespace(
            revoke_user_subscription=AsyncMock(
                return_value={"subscriptionUrl": "https://sub.example.test/new-short-uuid"}
            )
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value={"user_id": "panel-uuid"}),
            panel_service=panel_service,
        )
        settings = _settings()
        self._patch_context(
            settings=settings,
            subscription_service=subscription_service,
            db_user=_db_user(),
        )
        send_email = AsyncMock(return_value=True)
        prepare_links = AsyncMock(
            return_value=("happ://crypt4/encrypted", "https://redirect.example.test")
        )
        with (
            patch.object(reissue_module, "send_user_notification_email", send_email),
            patch.object(reissue_module, "prepare_config_links", prepare_links),
            patch.object(
                reissue_module,
                "subscription_mini_app_install_url",
                return_value="https://miniapp.example.test/install",
            ),
        ):
            response = await subscription_reissue_route(_JsonRequest())

        assert response.status == 200
        body = _response_body(response)
        assert body == {"ok": True, "email_sent": True}
        panel_service.revoke_user_subscription.assert_awaited_once_with("panel-uuid")
        prepare_links.assert_awaited_once_with(settings, "https://sub.example.test/new-short-uuid")
        send_email.assert_awaited_once()
        email_kwargs = send_email.await_args.kwargs
        assert email_kwargs["subject_key"] == "email_subscription_reissue_subject"
        assert email_kwargs["dashboard_url"] == "https://miniapp.example.test/install"
        assert email_kwargs["cta_label_key"] == "email_subscription_reissue_cta"
        assert email_kwargs["audit_event_type"] == "subscription_reissue_email"
        reissue_module.invalidate_webapp_user_caches.assert_awaited_once_with(
            settings, 42, include_devices=True, include_me=True
        )

    async def test_email_failure_still_reports_reissue_with_email_sent_false(self):
        panel_service = SimpleNamespace(
            revoke_user_subscription=AsyncMock(
                return_value={"subscriptionUrl": "https://sub.example.test/new-short-uuid"}
            )
        )
        subscription_service = SimpleNamespace(
            get_active_subscription_details=AsyncMock(return_value={"user_id": "panel-uuid"}),
            panel_service=panel_service,
        )
        self._patch_context(
            settings=_settings(),
            subscription_service=subscription_service,
            db_user=_db_user(),
        )
        send_email = AsyncMock(return_value=False)
        with (
            patch.object(reissue_module, "send_user_notification_email", send_email),
            patch.object(
                reissue_module,
                "prepare_config_links",
                AsyncMock(return_value=(ANY, ANY)),
            ),
            patch.object(reissue_module, "subscription_mini_app_install_url", return_value=None),
            patch.object(
                reissue_module,
                "subscription_mini_app_path_url",
                return_value="https://miniapp.example.test/",
            ),
        ):
            response = await subscription_reissue_route(_JsonRequest())

        assert response.status == 200
        assert _response_body(response) == {"ok": True, "email_sent": False}
        email_kwargs = send_email.await_args.kwargs
        assert email_kwargs["dashboard_url"] == "https://miniapp.example.test/"
        assert email_kwargs["cta_label_key"] == "email_user_notification_cta"
